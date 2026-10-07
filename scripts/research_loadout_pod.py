"""Loadout pod research (research/docs/loadout-pod-F5FEE03DCFDB.md): can a custom stratagem's pod deliver a JAR-5
Dominator primary configured full-auto, plus an M-1000 Maxigun backpack that feeds that JAR-5's ammunition, under the
instance-local rule? Read-only, offline: the game.dll image of the retained snapshots, the pinned entity tables (scan
toolkit) and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written anywhere.

Proves [C] (pinned code), observes [O] (snapshots, pinned data):

1. Pickup slot (q1). The interaction handler 0x97C2D0 switches on the zone's InteractType through a 52-entry jump
   table (0x97F424). PickupWeaponPrimary (1), PickupWeaponSidearm (2) and PickupWeaponSupport (3) share one case
   (0x97C940) whose inventory slot is 1, 2 or 3 respectively; PickupHellpod (13) goes to the generic case. The JAR-5's
   InteractableComponentData has exactly one zone, PickupWeaponPrimary; every support rack item has two zones,
   PickupHellpod and its own pickup [O]. LoadoutEntry item type: JAR-5 PrimaryWeapon (1), Maxigun SupportWeapon (2),
   its backpack Backpack (6) [O].
2. Rack items (q1). A hellpod rack spawns its items only from its creation builder (0x938A20 -> 0x934CD0, the only
   caller), from the resolved HellpodRackComponentData (0x500640: the entity's private copy at +0xA0 if one exists,
   else the shared type record). The copy is keyed by the rack entity, so no copy can exist before the items spawn:
   no instance-local rack path [C].
3. Fire modes (q2). The WeaponData resolver 0x509A40 prefers the entity's private copy (map +0x70, copies +0xB0,
   0x4D0 bytes) over the shared type record. The game's own copy routine 0x75F080 (component world + 0xE9FB80, the
   entity handle, a delta entry {kind, first, count}) copies the type record and applies count patches (count 0: an
   unmodified copy; an entity with a copy only gets the patches; it grows its own storage). The fire-mode selector
   (0x7552D0 case Firemode) counts the non-zero modes of the RESOLVED record's +0x90/+0x94/+0x98, advances the
   per-instance index (state +4 bits 12-13), and the current mode (state +0) becomes resolved[index] (0x7567F0); the
   owner's wielder update re-derives state +0 from the resolved record (0x6128B0) and replicates it (field
   0x49C250A6). Only three slots are ever selected: 0x7567F0 maps index 3 to None [C].
4. Ammunition (q3). The weapon's ammunition source is chosen by a per-weapon flag word built at creation from its
   components (0x73FCE0; the getter 0x742900: bit 9 heat, bit 7 magazine, bit 8 rounds, bit 10 linked ammo, bit 12
   another). A linked-ammo weapon's own instance record (+0x48, 0x24 bytes) holds the linked deposit entity at +0;
   consumption goes to the deposit consume routine 0x87F970 (owner writes, a non-owner asks the owner). The JAR-5 has
   no WeaponLinkedAmmoComponentData, so it has no such instance and its flag word routes to its magazine [C][O].
5. Ownership (q4). The owner-gated paths: the fire-mode field writes and the deposit's network writes are queued only
   for objects owned here (handle +0x14 bit 0; research deposit-limits fieldQueue); the copy routines take no
   ownership test (research peer-messaging) [C].

Output: research/loadout-pod-F5FEE03DCFDB.json (--check compares a fresh build with the committed file).
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
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/loadout-pod-F5FEE03DCFDB.json'
POD_PAYLOADS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
FIRE_MODES = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'

WORLD = 0x346BF98                       # entity manager (WeaponData type table at world +0xF12BD8)
WEAPON_DATA = 0x3326CE0                 # WeaponData manager = component world + 0xE9FB80
PROJECTILE_WEAPON = 0x33266D8           # ProjectileWeapon manager = component world + 0xF0B3B8
WEAPON = 0x3326660                      # Weapon manager (per-weapon flag word at +0x50, 0x28 bytes)
LINKED_AMMO = 0x3326AA8                 # WeaponLinkedAmmo manager
DEPOSIT = 0x33265E8                     # Deposit manager (research deposit-limits)
RACK = 0x3326A58                        # HellpodRack manager (research support-delivery)
INVENTORY = 0x3326738                   # Inventory manager (research event-wielder)
JUMP_TABLE = 0x97F424
NAME_TABLE = 0x21417E0                  # InteractType names (pointers), index = value
WD_TYPE = {'table': 0xF12BD8, 'slots': 0x2DA, 'records': 0x2DA0, 'stride': 0x4D0}
WD_LAYOUT = {'entityMap': 0x30, 'handles': 0x48, 'records': 0x58, 'recordStride': 0x3F0, 'state': 0x60,
    'stateStride': 12, 'copyMap': 0x70, 'reverseMap': 0x90, 'copyCount': 0xA8, 'copies': 0xB0, 'copyStride': 0x4D0}
MODES = {'burst': 0x8C, 'primary': 0x90, 'secondary': 0x94, 'tertiary': 0x98, 'quaternary': 0x9C,
    'functionLeft': 0xB8, 'functionRight': 0xBC, 'infiniteAmmoCandidate': 0x3B8}
ENTITIES = {'JAR-5 Dominator': 0x80F1A156D9FA1E36, 'M-1000 Maxigun': 0x43A58CB89CFA197C,
    'M-1000 Maxigun Backpack': 0x056DE1C5E21E723E, 'M-105 Stalwart': 0xA6A735ACCB4A327F,
    'SG-88 Break-Action Shotgun': 0x52071F49263415E4}
MAXIGUN_RACK = '0x73B63D637973C7A4'
INTERACT = {1: 'PickupWeaponPrimary', 2: 'PickupWeaponSidearm', 3: 'PickupWeaponSupport', 13: 'PickupHellpod',
    29: 'PickupBackpack'}

GAME = {
    'pickupSlot': [
        (0x97C928, 'cmp eax, 0x33', None, 'the interaction handler: InteractType - 1 within 52 cases ...'),
        (0x97C933, 'mov ecx, dword ptr [r8 + rax*4 + 0x97f424]', None, '... through the jump table 0x97F424'),
        (0x97C93E, 'jmp rcx', None, '... dispatched'),
        (0x97C8C0, 'mov edx, 1', None, 'edx = 1 on entry to the weapon case'),
        (0x97C940, 'cmp r14d, 1', None, 'the weapon case (types 1, 2, 3): PickupWeaponPrimary ...'),
        (0x97C944, 'mov eax, 3', None, '... else the support slot (3) ...'),
        (0x97C949, 'cmove eax, edx', None, '... PickupWeaponPrimary: slot 1'),
        (0x97C9DF, 'cmp r14d, 1', None, 'the slot passed on: PickupWeaponPrimary keeps 1 ...'),
        (0x97C9F0, 'cmp r14d, 2', None, '... PickupWeaponSidearm ...'),
        (0x97C9F4, 'mov ecx, 2', None, '... slot 2'),
        (0x97D643, 'test byte ptr [r15 + 0x14], 1', None, 'the generic case (PickupHellpod 13 ...): owned here only'),
    ],
    'rackSpawn': [
        (0x52FE9C, 'call 0x938a20', None, 'the rack component\'s creation builder ...'),
        (0x938A55, 'mov rsi, qword ptr [rip + {rip}]', RACK, '... (the HellpodRack manager) ...'),
        (0x938B2E, 'call 0x934cd0', None, '... spawns the rack\'s items (its only caller)'),
        (0x934D15, 'call 0x500640', None, 'the item spawner resolves the rack record ...'),
        (0x500662, 'mov r11, qword ptr [rip + {rip}]', RACK, '... the resolver: the rack manager ...'),
        (0x500694, 'mov rdi, qword ptr [r11 + 0x60]', None, '... its private-copy map (keyed by the rack entity) ...'),
        (0x5006E2, 'imul rax, rax, 0x238', None, '... a private copy (0x238 bytes) ...'),
        (0x5006E9, 'add rax, qword ptr [r11 + 0xa0]', None, '... at +0xA0 ...'),
        (0x5006FC, 'jmp 0x4ffff0', None, '... else the shared type record'),
    ],
    'weaponDataResolver': [
        (0x509A62, 'mov r11, qword ptr [rip + {rip}]', WEAPON_DATA, 'the WeaponData resolver: its manager ...'),
        (0x509A97, 'mov rdi, qword ptr [r11 + 0x70]', None, '... the entity -> private copy map ...'),
        (0x509AE2, 'imul rax, rax, 0x4d0', None, '... a private copy (0x4D0 bytes, the whole record) ...'),
        (0x509AE9, 'add rax, qword ptr [r11 + 0xb0]', None, '... at +0xB0 ...'),
        (0x509AFC, 'jmp 0x509570', None, '... else the shared type record'),
        (0x5095F1, 'imul rax, rcx, 0x4d0', None, 'the shared type record (0x4D0 bytes) ...'),
        (0x5095F8, 'add rax, 0x2da0', None, '... after the 730-row index'),
    ],
    'weaponDataCopy': [
        (0x575ABE, 'lea rcx, [r13 + 0xe9fb80]', None, 'the game\'s own caller: component world + 0xE9FB80 ...'),
        (0x575AC5, 'mov r8, r14', None, '... the delta entry ...'),
        (0x575AC8, 'mov rdx, r12', None, '... the entity handle ...'),
        (0x575ACB, 'call 0x75f080', None, '... the WeaponData copy routine'),
        (0x576AA7, 'lea rcx, [r13 + 0xf0b3b8]', None, 'the same switch\'s ProjectileWeapon case ...'),
        (0x576AB4, 'call 0x61af10', None, '... (the routine custom_weapons already calls)'),
        (0x75F0C9, 'mov r11, qword ptr [rcx + 0x70]', None, 'the copy routine: the entity\'s existing copy ...'),
        (0x75F11E, 'call 0x515540', None, '... gets the patches only'),
        (0x75F14D, 'call 0x509570', None, 'else the shared type record ...'),
        (0x75F137, 'mov edx, 0x4d0', None, '... into 0x4D0 bytes of scratch ...'),
        (0x75F1FB, 'call 0x515540', None, '... patched ...'),
        (0x75F209, 'mov dword ptr [rsi + 0xa8], eax', None, '... the copy count + 1 ...'),
        (0x75F217, 'call 0x75ed60', None, '... the storage grown when full (the routine checks its capacity) ...'),
        (0x75F227, 'call 0x172f790', None, '... entity -> copy ...'),
        (0x75F239, 'call 0x172f790', None, '... copy -> entity ...'),
        (0x75F245, 'add rdx, qword ptr [rsi + 0xb0]', None, '... and the record stored'),
        (0x515554, 'mov ebx, dword ptr [rdx + 4]', None, 'the patch loop: the first patch ...'),
        (0x51555A, 'mov r9d, dword ptr [rdx + 8]', None, '... and the count ...'),
        (0x51556A, 'jae 0x51559e', None, '... count 0: no patch is read'),
        (0x75E161, 'mov r9, qword ptr [rbx + 0xb0]', None, 'the instance removed: its copy dropped with it'),
    ],
    'fireModeSelector': [
        (0x75545E, 'shr esi, 0xc', None, 'the Firemode press: the index (state +4 bits 12-13) ...'),
        (0x755471, 'call 0x509a40', None, '... the RESOLVED record (the private copy when one exists) ...'),
        (0x755476, 'cmp dword ptr [rax + 0x90], edi', None, '... counts its primary ...'),
        (0x755480, 'cmp dword ptr [rax + 0x94], 0', None, '... secondary ...'),
        (0x75548D, 'cmp dword ptr [rax + 0x98], 0', None, '... and tertiary mode ...'),
        (0x75549F, 'div edi', None, '... index = (index + 1) mod count ...'),
        (0x7554B7, 'mov dword ptr [r13 + r12*4 + 4], r14d', None, '... stored in the instance state ...'),
        (0x7554AF, 'mov edx, 0x31f86165', None, '... and replicated ...'),
        (0x7554DD, 'call 0x7567f0', None, '... the mode at that index ...'),
        (0x7554EC, 'call 0x755f90', None, '... becomes the current mode'),
        (0x756810, 'call 0x509a40', None, 'the mode at an index: the resolved record ...'),
        (0x75683B, 'mov eax, dword ptr [rax + 0x90]', None, '... index 0 ...'),
        (0x75682F, 'mov eax, dword ptr [rax + 0x94]', None, '... 1 ...'),
        (0x756823, 'mov eax, dword ptr [rax + 0x98]', None, '... 2 ...'),
        (0x756805, 'xor eax, eax', None, '... any other index: None (the quaternary slot is never selected)'),
        (0x612C71, 'shr r8d, 0xc', None, 'the wielder update: the instance index ...'),
        (0x612C79, 'call 0x7567f0', None, '... the resolved record\'s mode at it ...'),
        (0x612CA4, 'test byte ptr [rdx + 0x14], 1', None, '... on the machine that owns the weapon ...'),
        (0x612CD7, 'mov dword ptr [rax + rcx*4], r8d', None, '... is written into state +0 (the current mode) ...'),
        (0x612CEB, 'mov edx, 0x49c250a6', None, '... and replicated (0x49C250A6)'),
        (0x7515CB, 'call 0x509a40', None, 'the instance build: the resolved record ...'),
        (0x7516B6, 'mov ebx, dword ptr [rax + 0x90]', None, '... its primary mode ...'),
        (0x752096, 'mov dword ptr [rax + r13*4], ebx', None, '... is the initial current mode'),
        (0x75249F, 'mov eax, dword ptr [r15 + 0xb8]', None, 'the instance record copies the input bindings ...'),
        (0x7524A6, 'mov dword ptr [rbp + 0x350], eax', None, '... to +0x350 (read by the weapon-function query)'),
        (0x755D48, 'mov eax, dword ptr [rax + rcx*4]', None, 'the Firemode query: state +0, the current mode'),
    ],
    'ammoSource': [
        (0x742998, 'cmp byte ptr [rax + 0x3b8], sil', None, 'the rounds getter: resolved WeaponData +0x3B8 set ...'),
        (0x7429BE, 'bt eax, 9', None, 'the flag word: bit 9 heat ...'),
        (0x742A3C, 'jns 0x742ac0', None, '... bit 7 the magazine ...'),
        (0x742AC0, 'bt eax, 8', None, '... bit 8 weapon rounds ...'),
        (0x742B43, 'bt eax, 0xa', None, '... bit 10 linked ammunition ...'),
        (0x742B52, 'call 0x7725b0', None, '... the linked deposit\'s amount ...'),
        (0x742B59, 'bt eax, 0xc', None, '... bit 12 another source'),
        (0x74028B, 'cmp byte ptr [rax + 0x3b8], r14b', None, 'the flag word is built at creation ...'),
        (0x740294, 'or dword ptr [rdi + rbx*8], 0x800', None, '... bit 11 from WeaponData +0x3B8'),
        (0x50B302, 'mov r11, qword ptr [rip + {rip}]', LINKED_AMMO, 'the linked-ammo resolver: its manager ...'),
        (0x50B386, 'add rax, qword ptr [r11 + 0xa0]', None, '... a private copy, else the type record'),
        (0x772518, 'mov eax, dword ptr [rax + rdx*4]', None, 'a linked weapon\'s own record +0: the linked entity ...'),
        (0x772527, 'mov r11, qword ptr [rip + {rip}]', DEPOSIT, '... looked up in the Deposit manager ...'),
        (0x772588, 'call 0x87f970', None, '... and its deposit consumed'),
        (0x771FA7, 'mov dword ptr [rax + rcx*4], r8d', None, 'the linked entity setter (record +0)'),
    ],
}


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def hexid(value):
    return '0x%016X' % value


def map_items(mem, header):
    """The game's open-addressing map {u64 slots, u32 capacity, u32 empty, u32 multiplier}: key -> value."""
    raw = mem.read(header, 20)
    if not raw:
        return {}
    slots, capacity, empty, _ = struct.unpack('<QIII', raw)
    table = mem.read(slots, capacity * 8) if slots and capacity else None
    out = {}
    for i in range(capacity if table else 0):
        key, value = struct.unpack_from('<II', table, i * 8)
        if key != empty and value != 0xFFFFFFFF:
            out[key] = value
    return out


def weapon_data_type(mem, resource):
    world = mem.ptr(mem.game + WORLD)
    table = world and mem.ptr(world + WD_TYPE['table'])
    if not table:
        return None
    i = resource % WD_TYPE['slots']
    for _ in range(WD_TYPE['slots']):
        key, index = struct.unpack('<QI', mem.read(table + i * 16, 12))
        if key == resource:
            return mem.read(table + WD_TYPE['records'] + index * WD_TYPE['stride'], WD_TYPE['stride'])
        if key == 0:
            return None
        i = (i + 1) % WD_TYPE['slots']
    return None


def modes_of(raw):
    return list(struct.unpack_from('<4I', raw, MODES['primary']))


def observe(name, labels):
    """Every WeaponData instance of one snapshot: its own state, its private copy (if any) against its type."""
    mem = base.Mem(name)
    try:
        wd = mem.ptr(mem.game + WEAPON_DATA)
        pw = mem.ptr(mem.game + PROJECTILE_WEAPON)
        out = {'snapshot': name, 'componentWorldAgrees': bool(wd and pw and wd - 0xE9FB80 == pw - 0xF0B3B8)}
        instances = map_items(mem, wd + WD_LAYOUT['entityMap']) if wd else {}
        copies = map_items(mem, wd + WD_LAYOUT['copyMap']) if wd else {}
        out['copyCount'] = mem.u32(wd + WD_LAYOUT['copyCount']) if wd else None
        handles, state, store = (mem.ptr(wd + WD_LAYOUT[k]) if wd else None for k in ('handles', 'state', 'copies'))
        weapons = mem.ptr(mem.game + WEAPON)
        weapon_index = map_items(mem, weapons + 0x28) if weapons else {}
        weapon_flags = mem.ptr(weapons + 0x50) if weapons else None
        rows = []
        for entity, index in sorted(instances.items(), key=lambda kv: kv[1]):
            handle = mem.read(mem.ptr(handles + index * 8), 0x18)
            resource, _, network, flags = struct.unpack_from('<QIII', handle, 0)
            current, word, _ = struct.unpack('<III', mem.read(state + index * WD_LAYOUT['stateStride'], 12))
            type_raw = weapon_data_type(mem, resource)
            row = {'entity': entity, 'resource': hexid(resource), 'label': labels(resource), 'networkId': network,
                'createdHere': bool(flags & 1), 'currentMode': current, 'modeIndex': (word >> 12) & 3,
                'typeModes': modes_of(type_raw) if type_raw else None, 'copy': None}
            if entity in copies:
                raw = mem.read(store + copies[entity] * WD_LAYOUT['copyStride'], WD_LAYOUT['copyStride'])
                row['copy'] = {'index': copies[entity], 'modes': modes_of(raw), 'equalsType': raw == type_raw,
                    'differingWords': ['0x%X' % o for o in range(0, len(raw), 4) if type_raw
                        and raw[o:o + 4] != type_raw[o:o + 4]]}
            if entity in weapon_index and weapon_flags:
                word = u32(mem.read(weapon_flags + weapon_index[entity] * 0x28, 4), 0)
                row['weaponFlags'] = [b for b in range(16) if word >> b & 1]
            rows.append(row)
        out['instances'] = rows
        linked = mem.ptr(mem.game + LINKED_AMMO)
        out['linkedAmmoInstances'] = len(map_items(mem, linked + 0x20)) if linked else None
        return out
    finally:
        mem.close()


def type_data():
    """The pinned entity tables: components, interaction zones, loadout entry, equipment, linked ammo, fire modes."""
    from scan import tables
    t = tables.pinned()

    def record(component, resource):
        c = t.component(component)
        r = c.record_of(resource)
        return (c.raw(r), len(c.owners(r))) if r is not None else (None, 0)

    out = {}
    for label, resource in ENTITIES.items():
        components = sorted(name[:-len('ComponentData')] for name in t.entity(resource))
        item = {'resource': hexid(resource), 'components': components}
        raw, owners = record('InteractableComponentData', resource)
        if raw:
            zones = [struct.unpack_from('<i', raw, 8 + 136 * i + 40)[0] for i in range(4)]
            item['interactZones'] = [INTERACT.get(z, z) for z in zones if z]
            item['interactableOwners'] = owners
        raw, _ = record('LoadoutEntryComponentData', resource)
        if raw:
            item['loadoutItemType'] = u32(raw, 4)
        raw, _ = record('EquipmentComponentData', resource)
        if raw:
            item['equipmentDropMode'] = struct.unpack_from('<i', raw, 136)[0]
        raw, owners = record('WeaponLinkedAmmoComponentData', resource)
        if raw:
            tag, mode, slot = struct.unpack_from('<QII', raw, 0)
            item['linkedAmmo'] = {'tag': hexid(tag), 'ammoMode': mode, 'inventorySlot': slot, 'owners': owners}
        raw, owners = record('WeaponDataComponentData', resource)
        if raw:
            item['weaponData'] = {'burstRounds': u32(raw, MODES['burst']), 'modes': modes_of(raw),
                'functions': list(struct.unpack_from('<2i', raw, MODES['functionLeft'])),
                'byte952': raw[MODES['infiniteAmmoCandidate']], 'owners': owners}
        out[label] = item
    wd = t.component('WeaponDataComponentData')
    flagged = sorted({t.label(o) for rec, owners in wd.owner_map().items() if wd.raw(rec)[952] for o in owners})
    member = next(m.describe() for m in wd.members() if m.describe()['offset'] == 952)
    return out, {'offset': 952, 'storage': member['storage'], 'nameLength': member['nameLength'],
        'nonZeroOwners': flagged}


def enum_lengths():
    import research_entity_authoring as entity_research
    from research_booster_authoring import TypeLibrary
    native = entity_research.Native()
    library = TypeLibrary(native.typelib, native.probe)
    return {name: {str(k): v for k, v in library.lengths(name).items()} for name in
        ('InteractType', 'InventorySlot', 'LoadoutItemType', 'EquipmentDropMode', 'FireMode')}


def build() -> dict:
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat = [p for rows in pins.values() for p in rows]
    mismatch = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(mismatch.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatch)

    # The interaction jump table and the InteractType name table (index = value).
    cases = {}
    for value in range(1, 0x35):
        target = (struct.unpack_from('<i', game.data, JUMP_TABLE + (value - 1) * 4)[0]) & 0xFFFFFFFF
        cases.setdefault('0x%X' % target, []).append(value)
    names = {}
    for value in range(1, 40):
        rva = game.pointer_rva(NAME_TABLE + value * 8)
        names[str(value)] = game.cstr(rva) if rva else None
    weapon_case = cases.get('0x97C940')
    if weapon_case != [1, 2, 3] or 13 in weapon_case:
        raise ValueError('the weapon pickup case changed: %r' % weapon_case)
    if [names[str(v)] for v in (1, 2, 3, 13, 29)] != ['PickupWeaponPrimary', 'PickupWeaponSidearm',
            'PickupWeaponSupport', 'PickupHellpod', 'PickupBackpack']:
        raise ValueError('the InteractType name table changed')

    from scan import tables
    pinned = tables.pinned()
    entities, byte952 = type_data()
    jar, maxigun, pack = (entities[k] for k in ('JAR-5 Dominator', 'M-1000 Maxigun', 'M-1000 Maxigun Backpack'))
    if jar['interactZones'] != ['PickupWeaponPrimary'] or 'WeaponLinkedAmmo' in jar['components'] \
            or 'WeaponMagazine' not in jar['components'] or jar['loadoutItemType'] != 1:
        raise ValueError('the JAR-5 type data changed: %r' % jar)
    if maxigun['interactZones'] != ['PickupHellpod', 'PickupWeaponSupport'] or maxigun['linkedAmmo']['inventorySlot'] != 6:
        raise ValueError('the Maxigun type data changed: %r' % maxigun)
    if pack['interactZones'] != ['PickupHellpod', 'PickupBackpack'] or 'Deposit' not in pack['components']:
        raise ValueError('the Maxigun backpack type data changed: %r' % pack)
    if jar['weaponData']['modes'] != [2, 3, 0, 0]:
        raise ValueError('the JAR-5 fire modes changed')

    observations = [observe(name, pinned.label) for name in SNAPSHOTS]
    jar_copies = [(o['snapshot'], r) for o in observations for r in o['instances']
        if r['label'] in ('jet_rifle', 'jet_rifle_phoenix') and r['copy']]
    pod = json.loads(POD_PAYLOADS.read_text(encoding='utf-8'))
    candidates = {c['resource']: c for c in pod['candidates']}
    rack = next(r for r in pod['racks'] if r['resource'] == MAXIGUN_RACK)
    primaries = [c for c in pod['candidates'] if c['category'] == 'primary_weapon']
    residency = json.loads(RESIDENCY.read_text(encoding='utf-8'))['catalog']
    fire = json.loads(FIRE_MODES.read_text(encoding='utf-8'))
    jar_fire = next(w for w in fire['weapons'] if w['weapon'] == 'JAR-5 Dominator')

    return {
        'schemaVersion': 1,
        'build': 'F5FEE03DCFDB',
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'writes': 0,
        'protectionChanges': 0,
        'pins': pins,
        'pinnedBytesMismatchPerSnapshot': mismatch,
        'globals': {'weaponData': '0x%X' % WEAPON_DATA, 'projectileWeapon': '0x%X' % PROJECTILE_WEAPON,
            'weapon': '0x%X' % WEAPON, 'linkedAmmo': '0x%X' % LINKED_AMMO, 'deposit': '0x%X' % DEPOSIT,
            'rack': '0x%X' % RACK, 'inventory': '0x%X' % INVENTORY,
            'weaponDataIsComponentWorldPlus': '0xE9FB80'},
        'weaponDataLayout': {k: '0x%X' % v for k, v in WD_LAYOUT.items()},
        'weaponDataModes': {k: '0x%X' % v for k, v in MODES.items()},
        'interaction': {'jumpTable': '0x%X' % JUMP_TABLE, 'cases': cases, 'names': names,
            'weaponCaseSlots': {'PickupWeaponPrimary': 1, 'PickupWeaponSidearm': 2, 'PickupWeaponSupport': 3}},
        'enumAliasLengths': enum_lengths(),
        'entities': entities,
        'weaponDataByte952': byte952,
        'maxigunRack': {'resource': rack['resource'], 'path': rack['path'], 'ownerCount': rack['ownerCount'],
            'spawnPayloadSize': rack['spawnPayloadSize'],
            'slots': [{'index': s['index'], 'item': s['item'], 'applyDeltas': s['applyDeltas']}
                for s in rack['slots'] if s['active']]},
        'podPayloadCatalog': {'jar5': candidates.get(hexid(ENTITIES['JAR-5 Dominator'])),
            'primaryCandidates': len(primaries),
            'primariesInRacksOrLoot': [c['path'] for c in primaries if c['rackPayloadOf'] or c['worldLootTables']]},
        'packages': {'jar5': residency.get('player_weapon/JAR-5 Dominator', {}).get('dependency'),
            'maxigunBackpack': residency.get('backpack/M-1000 Maxigun Backpack', {}).get('dependency')},
        'fireModeCatalog': {k: jar_fire[k] for k in ('slots', 'modes', 'selector', 'state', 'maxModes')},
        'observations': observations,
        'jar5PrivateCopiesObserved': [{'snapshot': s, 'entity': r['entity'], 'label': r['label'],
            'modes': r['copy']['modes'], 'differingWords': r['copy']['differingWords']} for s, r in jar_copies],
        'answers': ANSWERS,
        'design': DESIGN,
        'stages': STAGES,
        'refused': REFUSED,
        'open': OPEN,
    }


ANSWERS = {
    'q1_primaryFromPod': {
        'pickupIntoPrimarySlot': {'label': 'CONFIRMED', 'evidence': 'interaction handler 0x97C2D0 jump table 0x97F424: '
            'types 1/2/3 share case 0x97C940, which passes inventory slot 1 for PickupWeaponPrimary, 2 sidearm, 3 '
            'support; the JAR-5 InteractableComponentData has one zone, PickupWeaponPrimary (1); InteractType values '
            'from the game.dll name table 0x21417E0 (index = value); InventorySlot 1 = Primary by alias length and '
            'Filediver order (corroboration)'},
        'vanillaLoosePrimaries': {'label': 'PLAUSIBLE', 'evidence': 'no rack or bunker loot table names a primary (pod '
            'payload research); every one of the 67 primary entities carries a PickupWeaponPrimary zone; the after-'
            'reinforce snapshot still holds the dead body\'s primary (entity 605) beside the new one (855), while its '
            'sidearm was replaced'},
        'rackDeliversPrimary': {'label': 'CONFIRMED (refused)', 'evidence': 'a rack slot is a u64 entity reference in '
            'the SHARED HellpodRack type record; the items spawn only inside the rack entity\'s creation builder '
            '(0x52FE9C -> 0x938A20 -> 0x934CD0) from the resolved record (0x500640); a private rack copy is keyed by '
            'the rack entity, so none can exist before its items spawn. No instance-local rack path: a JAR-5 in a '
            'pod rack would be a shared write (and primaries are INCOMPATIBLE in the pod-payload catalogue)'},
        'jar5InRackInteractable': {'label': 'UNKNOWN', 'evidence': 'every rack item has a PickupHellpod (13) zone '
            'plus its own pickup zone; the JAR-5 has no PickupHellpod zone. Moot under the refusal above'},
        'nearestAlternative': {'label': 'PLAUSIBLE', 'evidence': 'a Runtime-spawned JAR-5 beside the call\'s own pod: '
            'the game\'s spawn request 0xFD9710 (research pelican "spawn"), resource-locked as native_spawn_gatling '
            'is (live-proven for the Gatling Sentry); standalone weapon entities are vanilla (bunker loot weapons in '
            'the mission snapshots carry WeaponData instances, copies and pickup zones). The entity is new, so it is '
            'instance-local by construction'},
    },
    'q2_fullAutoOneInstance': {
        'privateCopy': {'label': 'CONFIRMED', 'evidence': 'resolver 0x509A40 prefers the entity\'s private copy (map '
            '+0x70, copies +0xB0, 0x4D0 = the whole WeaponDataComponentData); the game\'s own copy routine 0x75F080 '
            '(component world + 0xE9FB80, handle, delta {kind, first, count}): count 0 gives an unmodified copy, an '
            'existing copy only gets patches; the copy is dropped with the instance (0x75E020)'},
        'jar5CopiesExistInVanilla': {'label': 'CONFIRMED (observed)', 'evidence': 'the ship snapshot\'s equipped '
            'JAR-5 (entity 252) has a private copy whose modes equal the type\'s (2, 3, 0, 0) and which differs only '
            'in customization words; loose bunker MG-43s carry copies too'},
        'whoReadsTheModeSet': {'label': 'CONFIRMED', 'evidence': 'the Firemode press (0x7552D0) counts the non-zero '
            'modes of the RESOLVED record (+0x90, +0x94, +0x98) and advances the instance index (state +4 bits '
            '12-13); 0x7567F0 maps the index to the resolved record\'s mode; the owner\'s wielder update (0x6128B0) '
            're-derives the current mode (state +0) from it and replicates it (0x49C250A6); the instance build sets '
            'the initial current mode from the resolved primary (0x7516B6)'},
        'whereTheCurrentModeLives': {'label': 'CONFIRMED', 'evidence': 'WeaponData manager +0x60, 12 bytes per '
            'instance: +0 the current FireMode, +4 flags with the mode index in bits 12-13 (all retained instances '
            'show index 0 and their type\'s primary)'},
        'reseeding': {'label': 'STRONG', 'evidence': 'the mode set is never copied into the 0x3F0 instance record '
            '(0x752370 copies only the input bindings +0xB8/+0xBC to +0x350); it is read live through the resolver, '
            'so a write to the private copy takes effect at the next press/update; nothing found that rewrites a '
            'copy after creation except new deltas through 0x75F080'},
        'instanceLocal': {'label': 'CONFIRMED', 'evidence': 'the copy is keyed by the one entity (map +0x70 / reverse '
            '+0x90) and removed with it; the shared type record is not touched; the copy routines take no ownership '
            'test (peer-messaging research), so every machine has its own copy'},
        'quaternarySlot': {'label': 'CONFIRMED', 'evidence': 'the selector counts three slots and 0x7567F0 returns '
            'None for index 3: +0x9C is never selected. docs/fire-modes.md says up to four; flag for review'},
    },
    'q3_backpackFedAmmo': {
        'maxigunLink': {'label': 'CONFIRMED', 'evidence': 'the Maxigun\'s WeaponLinkedAmmoComponentData (tag '
            '0x0000010000000000, inventory slot 6 Backpack) gives it a linked-ammo INSTANCE (manager 0x3326AA8, '
            'record 0x24 bytes) whose +0 is the linked deposit entity; the rounds getter (0x742900) takes bit 10 of '
            'the weapon flag word to that instance (0x7725B0) and consumption goes to the deposit consume routine '
            '0x87F970 through 0x772470'},
        'perInstanceOrType': {'label': 'STRONG', 'evidence': 'the link itself is per instance (record +0, setter '
            '0x771F20), but the instance exists only for an entity whose TYPE lists WeaponLinkedAmmoComponentData, '
            'and the flag word that routes the ammunition (bit 10 linked, bit 7 magazine) is built once at creation '
            'from the components (0x73FCE0). Observed: the only flag-10 weapon in the mission snapshots is the SEAF '
            'gun, the only linked-ammo instance'},
        'nativeLinkForJar5': {'label': 'CONFIRMED (blocked)', 'evidence': 'the JAR-5 type has no '
            'WeaponLinkedAmmoComponentData (it owns WeaponMagazine); no linked-ammo instance can exist for it; a '
            'component cannot be added to a live entity; flipping its flag word would route to a lookup that fails'},
        'roundsLogic': {'label': 'STRONG', 'evidence': 'a deposit is a counter: its amount is consumed by count, the '
            'projectile comes from the weapon\'s own ProjectileWeapon / magazine; a Runtime feed that never changes '
            'the JAR-5\'s round leaves its projectile logic untouched'},
        'infiniteAmmoCandidate': {'label': 'PLAUSIBLE', 'evidence': 'WeaponData +952 (UINT8, hidden name 13 = '
            '"infinite_ammo") is set only on the arc thrower, the SEAF gun, two cameras and a mech shield; the '
            'getters test it and creation turns it into flag bit 11 (0x740294). Because the flag is built once at '
            'creation, a private-copy write after creation is not shown to take effect: research lead only'},
        'nearestAlternative': {'label': 'PLAUSIBLE', 'evidence': 'a Runtime "magazine top-up from the pack": while the '
            'call\'s JAR-5 is held by the player wearing the call\'s Maxigun backpack, move rounds from that '
            'backpack\'s deposit into the JAR-5\'s own magazine (custom_weapons magazine members) in small guarded '
            'steps. A Runtime behaviour, not a native link'},
    },
    'q4_multiplayer': {
        'spawnAuthority': {'label': 'STRONG', 'evidence': 'rack contents spawn on the authority (support-delivery); '
            'a Runtime spawn runs where it is called (the Pelican is host-spawned); handle +0x14 bit 0 = created here'},
        'modeState': {'label': 'CONFIRMED', 'evidence': 'the current mode and its index are replicated fields '
            '(0x49C250A6, 0x31F86165) written only where the weapon is owned (0x612CA4; queue 0xFD97E0 skips '
            'objects not owned here)'},
        'privateCopies': {'label': 'CONFIRMED', 'evidence': 'not replicated: the host\'s private ProjectileWeapon copy '
            'showed on the host only (r2 live); each machine must make its own WeaponData copy of the correlated '
            'entity (the Gas EAT provenance pattern: network ids published, each Runtime converts its own copy)'},
        'deposit': {'label': 'CONFIRMED', 'evidence': 'deposit consume: the owner writes and queues "remaining", a '
            'non-owner sends 0x86A4E082 to the owner and predicts locally (deposit-limits)'},
        'pickupOwnership': {'label': 'UNKNOWN', 'evidence': 'whether a picked-up weapon or backpack migrates its '
            'network ownership to the picker is not traced; the Gas EAT live test only shows the entity persists '
            'across pickup and its rounds name each machine\'s own copy as source'},
    },
}

DESIGN = {
    'shape': {
        'carrier': "{beacon='support', prefer_families={'support'}}",
        'delivery': "{family='support', items={{donor=hd2.support_weapon('M-1000 Maxigun')}}, "
            "extra={{weapon=hd2.weapon('JAR-5 Dominator'), at='pod', modify={fire_modes={'automatic','single',"
            "'burst'}}, ammo_source={backpack='M-1000 Maxigun Backpack'}}}}",
        'notes': [
            'the native Maxigun pod delivers its own weapon and backpack (its unshared rack 0x73B63D637973C7A4, '
            'slot 0 weapon, slot 1 backpack); both are captured as ctx.items',
            'extra: a Runtime-spawned item, placed beside the call\'s pod once the pod is captured; typed handle '
            'only (hd2.weapon for primaries), resource-locked spawn; its loadout package (0x10A7605527187EF5) is an '
            'asset of the call and must be resident before the spawn (ASSET_UNAVAILABLE otherwise)',
            'modify.fire_modes: the item\'s own WeaponData private copy (0x75F080 count 0, skipped when it has one), '
            'then its +0x90/+0x94/+0x98 written in one guarded transaction; the type record compared whole before '
            'and after; up to three modes (the selector never selects the fourth)',
            'ammo_source.backpack: names one of the SAME call\'s captured backpacks; Runtime behaviour, refused at '
            'registration unless the backpack has a Deposit and the weapon owns a magazine',
        ],
    },
    'whyNotRack': 'the rack list is a shared definition and its items spawn during the rack\'s creation; no '
        'per-instance rack path exists (q1)',
    'feed': {
        'binding': 'the call\'s JAR-5 entity and the call\'s backpack entity (ctx.items), nothing else',
        'condition': 'the local player holds that JAR-5 (wielder slot 0, event-wielder research) and wears that '
            'backpack (inventory record; the backpack slot offset +12 is unproven and must be proven first)',
        'step': 'when the magazine is below capacity and the deposit is above 0: consume k from the deposit and add '
            'k rounds to the magazine entry and record, as one guarded transaction with expect values (a shot in '
            'between is a CONFLICT, retried next update)',
        'depositWrite': 'the native consume 0x87F970 (owner-aware, queues the network write) is preferred over a raw '
            'live-amount write; it is a new native call and needs its own entry-byte proof',
        'empty': 'deposit at 0 or pack removed: no top-up; the JAR-5 keeps its own magazines (vanilla)',
        'limits': 'magazine rounds are an 11-bit network field (2047); the deposit is 10 bits (1023)',
    },
}

STAGES = [
    {'stage': 'A', 'title': 'Drop a JAR-5 primary with the Maxigun pod', 'builds': 'resource-locked native spawn of '
        'the JAR-5 (the Gatling spawn pattern), placed at the captured pod; the JAR-5 package as an asset',
        'liveTest': 'solo host: call the stratagem; the pod opens with the Maxigun and its backpack; a JAR-5 lies '
        'beside it; pick it up: it replaces the primary (the old primary drops); fire it, reload it; a vanilla '
        'Maxigun call stays vanilla; a second call spawns a second JAR-5',
        'handoff': ['log SPAWNED: JAR-5 entity E (network id N) at the pod of beacon B', 'log PICKED: entity E in '
            'the primary slot (inventory record +0)', 'the package line (resident before the spawn)'],
        'refuseIf': 'package not resident; not the solo host; pod not captured; spawn entry bytes differ'},
    {'stage': 'B', 'title': 'Full-auto on that one JAR-5', 'builds': 'custom_weapons-style WeaponData private copy '
        '(0x75F080, count 0) and a guarded write of its mode slots',
        'liveTest': 'the spawned JAR-5 cycles single -> burst -> automatic (or starts automatic with '
        "{'automatic','single','burst'}); the player's own JAR-5 (if equipped) and any other JAR-5 keep single/burst",
        'handoff': ['log CONFIGURED fire modes: entity E copy modes (2,3,1) type modes (2,3,0) unchanged',
            'log the selector index and current mode after each press'],
        'refuseIf': 'the copy\'s modes differ from the type\'s before the write; the type record changes; the '
            'weapon is blocked in sdk/WeaponFireModeCapabilities.json'},
    {'stage': 'C', 'title': 'Pack-fed ammunition (Runtime top-up)', 'builds': 'prove the inventory backpack slot; '
        'the deposit consume native call; the top-up loop',
        'liveTest': 'solo host: wear the call\'s Maxigun backpack and hold the call\'s JAR-5: the magazine stays '
        'full while the backpack count falls one per round; take the pack off or empty it: the JAR-5 drains '
        'normally; resupply refills the pack; a vanilla Maxigun from another call is unaffected',
        'handoff': ['log FED: k rounds, deposit before/after, magazine before/after, read back',
            'log STOPPED: reason (not worn, deposit 0, not held)'],
        'refuseIf': 'either entity not the call\'s; the inventory proof missing; not the solo host'},
]

REFUSED = [
    {'request': 'a JAR-5 (or any primary) in the pod rack', 'reason': 'the rack list is a shared type record; its '
        'items spawn inside the rack\'s creation, so no private rack copy can precede them'},
    {'request': 'a native ammunition link from the JAR-5 to the backpack', 'reason': 'the JAR-5 type has no '
        'WeaponLinkedAmmoComponentData; components cannot be added to an entity'},
    {'request': 'writing the JAR-5 or Maxigun type records (fire modes, linked ammo, magazine)', 'reason': 'shared '
        'definitions: every JAR-5 and every Maxigun would change'},
    {'request': 'modifying the player\'s own equipped JAR-5', 'reason': 'not an entity the call spawned; would need '
        'an explicit rule change by the user'},
    {'request': 'removing the Maxigun weapon from the pod', 'reason': 'no reviewed per-instance removal of a rack '
        'item (its slot keeps the network id)'},
    {'request': 'a fourth fire mode', 'reason': 'the selector never selects the quaternary slot'},
    {'request': 'the infinite-ammo byte as the feed', 'reason': 'built into the weapon flag word at creation; '
        'unproven after creation and unnamed (PLAUSIBLE only)'},
]

OPEN = [
    'whether a Runtime-spawned JAR-5 behaves as a loose world weapon (physics, pickup prompt, default attachments)',
    'whether a picked-up weapon or backpack changes network owner (decides who writes the mode and the magazine)',
    'the inventory record\'s backpack slot (+12 is unproven) for the "wears the call\'s pack" check',
    'the deposit consume routine 0x87F970 as a callable native (arguments, entry bytes, thread)',
    'docs/fire-modes.md says up to four modes; the selector code selects three',
    'multiplayer: each Runtime making its own WeaponData copy of the correlated JAR-5 (network id published as for '
        'the Gas EAT launchers)',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true', help='fail when the committed JSON differs from a fresh build')
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, indent=1, sort_keys=False) + '\n'
    if args.check:
        current = OUTPUT.read_text(encoding='utf-8') if OUTPUT.is_file() else None
        if current != text:
            print('research/loadout-pod-F5FEE03DCFDB.json is stale')
            return 1
        print('research/loadout-pod-F5FEE03DCFDB.json is current')
        return 0
    OUTPUT.write_text(text, encoding='utf-8')
    print('wrote', OUTPUT.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
