"""Carrier pod items research (docs/research/carrier-pod-items-F5FEE03DCFDB.md): can a custom stratagem's pod deliver
any catalogued equipment (primaries, secondaries, throwables, support weapons, backpacks) by writing the CARRIER's own
rack for the mission, instead of redirecting the beacon to a donor whose rack is shared with vanilla calls? Read-only,
offline: the game.dll image of the retained snapshots, the pinned entity tables (scan toolkit), the pod payload,
package residency and loadout pod research, and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written.

Proves [C] (pinned code), observes [O] (pinned data, snapshots):

1. The rack spawner is type-agnostic (q2). Per RackAttach slot (64 bytes, 8 slots) of the resolved HellpodRack record,
   0x934CD0 skips a slot whose node (+8) or item (+0) is zero, applies customization deltas only when apply_deltas
   (+48) is set, spawns the item resource through the networked spawn 0xFDC140, writes its network id into the rack
   element slot and registers listener kind 0x3A (item -> rack entity, 0xB135F0). It reads no component of the item.
   The count is spawn_payload_size (+556), raised only by the type-keyed upgrade effect 0x119.
2. Placement (q2). The rack event places each item at its slot node (0x934690: 0x812540 / 0xBEC2D0) and enables
   InteractType 13 (PickupHellpod) on it unless record +560 is set (0x978AC0 only flips zones OF THAT TYPE: an item
   with none is unchanged and nothing is sent). The per-item bind (manager 0x33267F8, replicated 0xAD1808D1) is
   skipped for an item without a bind record (map miss).
3. Leaving the rack (q2). Every interaction case ends in the shared tail 0x97F28A -> 0xB57800, which runs the
   interacted entity's listeners: kind 0x3A releases it from its rack (0x9374D0: the owning machine resets the slot and
   sends 0xE87A1AF2). The weapon pickup case (types 1/2/3, slots 1/2/3) reaches that tail like every other case.
4. Item kinds (q2) [O]. Every entity's interaction zones, components (EntityBind, Explosive, Throwable, WeaponData),
   LoadoutEntry item type, vanilla rack membership and own loadout package: primaries and secondaries carry exactly one
   weapon pickup zone whose flags equal a support weapon's own pickup zone; the vanilla CQC-1 One True Flag rack item
   is picked up through that same case with no PickupHellpod zone and no EntityBind (vanilla precedent).
5. Carrier racks (q1) [O]. Per rack: record owner count, consumer stratagems, random/spawn sizes, active slots,
   read-only reason, and every reference to its resource outside the stratagem payload lists (all 270 component
   tables, the whole game.dll image).

Output: research/carrier-pod-items-F5FEE03DCFDB.json (--check compares a fresh build with the committed file).
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
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/carrier-pod-items-F5FEE03DCFDB.json'
POD_PAYLOADS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
RESIDENCY_DOMAIN = ROOT / 'domains/package_residency.lua'
LOADOUT_POD = ROOT / 'research/loadout-pod-F5FEE03DCFDB.json'

RACK = 0x3326A58                        # HellpodRack manager (research support-delivery)
BIND = 0x33267F8                        # the per-item bind manager the rack event writes (0x935E96)
JUMP_TABLE = 0x97F424                   # the interaction handler's case table (research loadout-pod)
NAME_TABLE = 0x21417E0                  # InteractType names, index = value
ZONE = {'first': 8, 'stride': 136, 'type': 40, 'count': 8}
ZONE_FLAGS = [(44, 'B', 17), (45, 'B', 13), (100, 'B', 20), (101, 'B', 21), (102, 'B', 23), (103, 'B', 29),
    (104, 'B', 25), (120, 'B', 13), (121, 'B', 16), (122, 'B', 29)]
SLOT_ZONE = {'primary': 1, 'sidearm': 2, 'support_weapon': 3, 'throwable': 14, 'backpack': 29}
HELLPOD_ZONE = 13
COMPARE = {'EAT-17 Expendable Anti-Tank': 0x80932FA0ED6901D3, 'M-1000 Maxigun': 0x43A58CB89CFA197C,
    'M-1000 Maxigun Backpack': 0x056DE1C5E21E723E, 'CQC-1 One True Flag': 0xB0F1B354BA1D38D8,
    'JAR-5 Dominator': 0x80F1A156D9FA1E36, 'P-2 Peacemaker': 0x05E4E5C2DB6E44A2, 'G-6 Frag': 0x4CE9EAB785A79B7B,
    'Grenade Box (pickup)': 0x97AF34FBF093409C, 'Supply Box (pickup)': 0xA94913CA014F7579}

GAME = {
    'rackCreation': [
        (0x938B2E, 'call 0x934cd0', None, 'the rack component\'s creation builder spawns its items (only caller)'),
        (0x934D15, 'call 0x500640', None, 'the spawner resolves the rack record (private copy, else the type record)'),
    ],
    'rackSpawner': [
        (0x9351C2, 'mov ecx, dword ptr [r12 + 0x228]', None, 'random_payload_size (record +552) ...'),
        (0x935201, 'je 0x9355b4', None, '... zero: the ordered slot path'),
        (0x9355ED, 'mov r13d, dword ptr [r12 + 0x22c]', None, 'the count: spawn_payload_size (record +556) ...'),
        (0x935635, 'cmp dword ptr [rsi + rax*8 + 0x3900], 0x119', None, '... raised only by a type-keyed upgrade '
            'effect 0x119 (keyed by the dispatched stratagem type)'),
        (0x9356F7, 'mov dword ptr [r12 + rax], 0x7fff', None, 'each rack element slot first reads "no item" (0x7FFF)'),
        (0x935705, 'cmp ecx, r13d', None, 'the loop stops once `count` items have spawned'),
        (0x935724, 'movd eax, xmm2', None, 'RackAttach +8: the node ...'),
        (0x93572E, 'je 0x935ad0', None, '... zero: the slot is skipped'),
        (0x935734, 'mov rdi, qword ptr [rsp + 0x60]', None, 'RackAttach +0: the item resource ...'),
        (0x93573C, 'je 0x935acb', None, '... zero ("empty"): skipped; nothing spawns and the count is not consumed'),
        (0x935745, 'cmp byte ptr [rbp - 0x70], r14b', None, 'RackAttach +48 apply_deltas: customization deltas '
            'are looked up only when it is set'),
        (0x9358FF, 'call 0x50ed80', None, 'no customization entry: the item\'s registry record ...'),
        (0x935910, 'call 0x74b010', None, '... and its default deltas'),
        (0x935A69, 'mov r8, rdi', None, 'the slot\'s item resource ...'),
        (0x935A73, 'call 0xfdc140', None, '... spawned as a networked entity (the pod content\'s own spawn); no '
            'component of the item is read by the spawner'),
        (0x935A7A, 'call 0xfd9af0', None, 'its network id ...'),
        (0x935A97, 'mov dword ptr [r12 + rax], ecx', None, '... into the rack element slot (what the Runtime '
            'capture reads)'),
        (0x935A85, 'mov r8d, 0x3a', None, 'listener kind 0x3A ...'),
        (0x935AA5, 'call 0xb135f0', None, '... registered on the item, naming the rack entity'),
        (0x935AEF, 'add rdx, 0x40', None, 'the next RackAttach (64 bytes)'),
        (0x935B00, 'cmp eax, 8', None, 'eight slots'),
    ],
    'rackPlacement': [
        (0x935E85, 'call 0x934690', None, 'the rack event places each slot item ...'),
        (0x934705, 'call 0x500640', None, '... from the resolved rack record (node and offsets, never the item) ...'),
        (0x9348A8, 'call 0x812540', None, '... at the slot node ...'),
        (0x9348F0, 'call 0xbec2d0', None, '... attached'),
        (0x93495B, 'cmp byte ptr [r15 + 0x230], 0', None, 'record +560 (UINT8, hidden name 27) clear ...'),
        (0x934968, 'mov r8d, 0xd', None, '... InteractType 13 (PickupHellpod) ...'),
        (0x934970, 'call 0x978ac0', None, '... is enabled on the item'),
        (0x978BAF, 'lea rcx, [rdx + 0x44]', None, 'the zone switch walks the item\'s instance zones ...'),
        (0x978BB3, 'cmp dword ptr [rcx], r12d', None, '... changing only zones of the given type ...'),
        (0x978BCA, 'add rcx, 0x68', None, '... (0x68 bytes each)'),
        (0x978BD3, 'cmp edi, eax', None, 'no zone of that type: no change, nothing replicated'),
        (0x935E96, 'mov rsi, qword ptr [rip + {rip}]', BIND, 'the per-item bind record (manager 0x33267F8) ...'),
        (0x935EB2, 'je 0x936029', None, '... an item without one is skipped (empty map) ...'),
        (0x935EE4, 'jne 0x936029', None, '... or a map miss'),
        (0x936010, 'mov edx, 0xad1808d1', None, 'otherwise the rack\'s network id is bound and replicated'),
    ],
    'rackLeave': [
        (0x97CA72, 'je 0x97d63a', None, 'the weapon pickup case (types 1/2/3) ends in the common path ...'),
        (0x97D63D, 'je 0x97f1c9', None, '... 0x97D63A -> the shared tail ...'),
        (0x97F28A, 'call 0xb57800', None, '... which runs the interacted entity\'s listeners for EVERY interaction '
            'type'),
        (0xB57910, 'btr eax, 0x1f', None, 'a listener\'s kind ...'),
        (0xB57914, 'cmp eax, 0x3a', None, '... 0x3A (the rack\'s) ...'),
        (0xB57A05, 'cmp dword ptr [rsp + 0xa8], 1', None, '... on a completed interaction ...'),
        (0xB57A71, 'call 0x9374d0', None, '... releases the item from its rack'),
        (0x937565, 'test byte ptr [rcx + 0x14], 1', None, 'the release runs where the rack is owned ...'),
        (0x937587, 'call 0xfd9ba0', None, '... each slot\'s network id -> entity ...'),
        (0x93758C, 'cmp dword ptr [rsp + 0x68], edi', None, '... the item\'s slot ...'),
        (0x9375AA, 'call 0x937c60', None, '... reset ...'),
        (0x9375EB, 'mov ecx, 0xe87a1af2', None, '... and announced'),
    ],
    'pickupSlot': [
        (0x97C928, 'cmp eax, 0x33', None, 'the interaction handler: InteractType - 1 within 52 cases ...'),
        (0x97C933, 'mov ecx, dword ptr [r8 + rax*4 + 0x97f424]', None, '... through the jump table 0x97F424'),
        (0x97C940, 'cmp r14d, 1', None, 'the weapon case (types 1, 2, 3): PickupWeaponPrimary ...'),
        (0x97C944, 'mov eax, 3', None, '... else the support slot (3) ...'),
        (0x97C949, 'cmove eax, edx', None, '... PickupWeaponPrimary: slot 1'),
        (0x97C9F0, 'cmp r14d, 2', None, '... PickupWeaponSidearm ...'),
        (0x97C9F4, 'mov ecx, 2', None, '... slot 2'),
    ],
    'throwablePickup': [
        (0x97D677, 'cmp esi, dword ptr [rip + {rip}]', None, 'PickupThrowable (14), its own case: the item ...'),
        (0x97D68F, 'call 0x172f670', None, '... looked up in its own component (a Throwable-only path) ...'),
        (0x97D7C1, 'call 0x9ab950', None, '... then an inventory routine whose count semantics are not traced'),
    ],
}


def hexid(value):
    return '0x%016X' % value


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def map_count(mem, header):
    """Live entries of the game's open-addressing map {u64 slots, u32 capacity, u32 empty, u32 multiplier}."""
    raw = mem.read(header, 20)
    if not raw:
        return None
    slots, capacity, empty, _ = struct.unpack('<QIII', raw)
    table = mem.read(slots, capacity * 8) if slots and capacity else b''
    return sum(1 for i in range(len(table) // 8)
        if struct.unpack_from('<II', table, i * 8)[0] != empty and struct.unpack_from('<II', table, i * 8)[1] != 0xFFFFFFFF)


def zones_of(ic, resource):
    rec = ic.record_of(resource)
    if rec is None:
        return None, None
    raw = ic.raw(rec)
    out, flags = [], {}
    for i in range(ZONE['count']):
        at = ZONE['first'] + ZONE['stride'] * i
        kind = struct.unpack_from('<i', raw, at + ZONE['type'])[0]
        if kind == 0:                   # InteractType 0 (alias length 17: None): an unused zone
            continue
        out.append(kind)
        flags.setdefault(str(kind), [struct.unpack_from('<' + f, raw, at + o)[0] for o, f, _ in ZONE_FLAGS])
    return out, flags


def live_package_keys():
    text = RESIDENCY_DOMAIN.read_text(encoding='utf-8')
    return sorted(set(re.findall(r'\["([a-z_]+/[^"]+)"\]=\{[^{}]*\["live"\]=true', text)))


# LoadoutEntry +4 (the item type): 1 = PrimaryWeapon, 2 = SupportWeapon, 6 = Backpack (research loadout-pod, alias
# lengths); 3 = every sidearm-path and melee sidearm entity, 4 = every throwable (observed here, unnamed).
LOADOUT_KIND = {1: 'primary', 2: 'support_weapon', 3: 'sidearm', 4: 'throwable', 6: 'backpack'}


def item_kind(key, loadout_type):
    """The kind by the entity's own LoadoutEntry item type; else its catalogue group (player weapons: unresolved)."""
    if loadout_type in LOADOUT_KIND:
        return LOADOUT_KIND[loadout_type]
    group = key.split('/')[0]
    return 'unresolved' if group == 'player_weapon' else group


def item_catalog(t, pod):
    """Every catalogued equipment entity: its kind, pickup zones, components, rack membership and package."""
    ic = t.component('InteractableComponentData')
    le = t.component('LoadoutEntryComponentData')
    in_rack = {}
    for rack in pod['racks']:
        for slot in rack['slots']:
            if slot['active'] and slot['item']:
                in_rack.setdefault(int(slot['item'], 16), set()).add(rack['resource'])
    live = set(live_package_keys())
    residency = json.loads(RESIDENCY.read_text(encoding='utf-8'))['catalog']
    items = []
    for key, entry in sorted(residency.items()):
        group = key.split('/')[0]
        if group not in ('player_weapon', 'support_weapon', 'backpack', 'throwable'):
            continue
        resource = int(entry['resource'], 16)
        rec = le.record_of(resource)
        loadout_type = u32(le.raw(rec), 4) if rec is not None else None
        kind = item_kind(key, loadout_type)
        zones, _ = zones_of(ic, resource)
        components = set(name[:-len('ComponentData')] for name in t.entity(resource))
        need = SLOT_ZONE.get(kind)
        has_pickup = bool(zones) and need in zones
        racked = sorted(in_rack.get(resource, ()))
        if kind in ('support_weapon', 'backpack'):
            if racked:
                verdict, label = 'VANILLA_RACK_ITEM', 'CONFIRMED'
            elif has_pickup or (zones and HELLPOD_ZONE in zones):
                verdict, label = 'NOT_OFFERED_NOT_A_RACK_ITEM', 'n/a'
            else:
                verdict, label = 'REFUSED_NO_PICKUP_ZONE', 'CONFIRMED'
        elif kind == 'primary':
            verdict, label = ('CANDIDATE', 'STRONG') if has_pickup else ('REFUSED_NO_PICKUP_ZONE', 'CONFIRMED')
        elif kind == 'sidearm':
            verdict, label = ('CANDIDATE', 'PLAUSIBLE') if has_pickup else ('REFUSED_NO_PICKUP_ZONE', 'CONFIRMED')
        elif kind == 'throwable':
            verdict, label = 'REFUSED_THROWABLE', 'UNKNOWN'
        else:
            verdict, label = 'REFUSED_UNRESOLVED', 'UNKNOWN'
        items.append({
            'key': key, 'label': entry['label'], 'kind': kind, 'resource': entry['resource'], 'path': entry['path'],
            'loadoutItemType': loadout_type, 'zones': zones, 'pickupZoneForSlot': need, 'hasPickupZone': has_pickup,
            'hellpodZone': bool(zones) and HELLPOD_ZONE in zones,
            'components': {c: c in components for c in ('EntityBind', 'Explosive', 'Throwable', 'WeaponData',
                'ProjectileWeapon', 'WeaponMagazine', 'WeaponLinkedAmmo', 'Backpack', 'LoadoutPackage', 'Attachable',
                'NetworkPhysics')},
            'vanillaRacks': racked,
            'package': (entry.get('dependency') or {}).get('package'),
            'packageVia': (entry.get('dependency') or {}).get('via'),
            'packageLiveProven': key in live,
            'verdict': verdict, 'confidence': label,
        })
    summary = {}
    for item in items:
        summary.setdefault(item['kind'], {}).setdefault(item['verdict'], 0)
        summary[item['kind']][item['verdict']] += 1
    return {'summary': summary, 'livePackageKeys': sorted(live), 'items': items}


def outside_references(t, image, pod):
    """Every reference to a rack resource outside the stratagem payload lists: all component tables, all of game.dll."""
    racks = {int(r['resource'], 16): r for r in pod['racks']}
    tables_hits = {}
    for name in t.component_names():
        component = t.component(name)
        for rec, owners in component.owner_map().items():
            raw = component.raw(rec)
            for off in range(0, len(raw) - 7, 4):
                value = struct.unpack_from('<Q', raw, off)[0]
                if value in racks:
                    tables_hits.setdefault(hexid(value), []).append({'component': name, 'record': rec, 'offset': off,
                        'owners': [t.label(o) for o in owners][:4]})
    dll_hits = {}
    for value in racks:
        found = image.find_bytes(struct.pack('<Q', value))
        if found:
            dll_hits[hexid(value)] = ['0x%X' % x for x in found]
    return {'entityTables': tables_hits, 'gameDll': dll_hits}


def carrier_racks(t, pod, refs, items):
    """Per rack: whether its record can be written as a carrier's own for a mission (exclusively owned)."""
    rk = t.component('HellpodRackComponentData')
    category = {c['resource']: c['category'] for c in pod['candidates']}
    by_resource = {i['resource']: i for i in items}
    out = []
    for rack in pod['racks']:
        resource = int(rack['resource'], 16)
        rec = rk.record_of(resource)
        raw = rk.raw(rec) if rec is not None else None
        active = [s for s in rack['slots'] if s['active']]
        usable = [s for s in active if s['item'] and s['node']]
        kinds = sorted({category.get(s['item']) or (by_resource.get(s['item']) or {}).get('kind') or 'unknown'
            for s in usable})
        consumers = [c['name'] for c in rack['consumers']]
        reasons = []
        if rack['ownerCount'] != 1:
            reasons.append('the HellpodRack record has %d owners' % rack['ownerCount'])
        if len(consumers) != 1:
            reasons.append('the rack is delivered by %d stratagem rows (%s)' % (len(consumers), ', '.join(consumers)))
        elif not rack['consumers'][0].get('catalogStratagem'):
            reasons.append('its one consumer row (%s) is not a catalogued player stratagem' % consumers[0])
        if rack['randomPayloadSize']:
            reasons.append('random_payload_size %d (slot order does not decide what spawns)' % rack['randomPayloadSize'])
        if any(k not in ('support_weapon', 'backpack') for k in kinds):
            reasons.append('an active slot delivers %s (not a support weapon or backpack pod)' % ', '.join(kinds))
        if hexid(resource) in refs['entityTables'] or hexid(resource) in refs['gameDll']:
            reasons.append('referenced outside the stratagem payload lists')
        if raw is not None and raw[560]:
            reasons.append('record +560 is set (the rack never enables PickupHellpod)')
        out.append({
            'resource': rack['resource'], 'path': rack['path'], 'consumers': consumers,
            'carrier': rack['consumers'][0].get('catalogStratagem') if len(consumers) == 1 else None,
            'recordOwnerCount': rack['ownerCount'], 'randomPayloadSize': rack['randomPayloadSize'],
            'spawnPayloadSize': rack['spawnPayloadSize'],
            'activeSlots': [{'index': s['index'], 'item': s['item'], 'node': s['node'], 'rackSide': s['rackSide'],
                'applyDeltas': s['applyDeltas']} for s in active],
            'slotsWithItems': [s['index'] for s in rack['slots'] if s['item']],
            'vanillaItemKinds': kinds, 'byte560': raw[560] if raw is not None else None,
            'maxItems': len(usable),
            'exclusiveCarrierRack': not reasons, 'reasons': reasons,
        })
    return out


def zone_comparison(t):
    ic = t.component('InteractableComponentData')
    out = {}
    for label, resource in COMPARE.items():
        zones, flags = zones_of(ic, resource)
        out[label] = {'resource': hexid(resource), 'zones': zones, 'flags': flags,
            'entityBind': 'EntityBindComponentData' in t.entity(resource)}
    return {'flagMembers': [{'zoneOffset': o, 'storage': f, 'nameLength': n} for o, f, n in ZONE_FLAGS],
        'entities': out}


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

    cases = {}
    for value in range(1, 0x35):
        target = (struct.unpack_from('<i', game.data, JUMP_TABLE + (value - 1) * 4)[0]) & 0xFFFFFFFF
        cases.setdefault('0x%X' % target, []).append(value)
    names = {}
    for value in (1, 2, 3, 13, 14, 29):
        rva = game.pointer_rva(NAME_TABLE + value * 8)
        names[str(value)] = game.cstr(rva) if rva else None
    case_of = {v: k for k, vs in cases.items() for v in vs}
    if [case_of[v] for v in (1, 2, 3)] != ['0x97C940'] * 3 or case_of[13] != '0x97D63A' or case_of[14] != '0x97D677':
        raise ValueError('the interaction cases changed: %r' % cases)

    bind = []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            mgr = mem.ptr(mem.game + BIND)
            rack = mem.ptr(mem.game + RACK)
            bind.append({'snapshot': name, 'bindInstances': map_count(mem, mgr + 0x20) if mgr else None,
                'racks': map_count(mem, rack + 0x28) if rack else None})
        finally:
            mem.close()

    from scan import tables
    from scan.xref import CodeImage
    t = tables.pinned()
    pod = json.loads(POD_PAYLOADS.read_text(encoding='utf-8'))
    catalog = item_catalog(t, pod)
    refs = outside_references(t, CodeImage.from_snapshot('game.dll'), pod)
    racks = carrier_racks(t, pod, refs, catalog['items'])
    flag = next(i for i in catalog['items'] if i['label'] == 'CQC-1 One True Flag')
    if flag['zones'] != [3] or flag['components']['EntityBind'] or not flag['vanillaRacks']:
        raise ValueError('the One True Flag precedent changed: %r' % flag)
    jar = next(i for i in catalog['items'] if i['label'] == 'JAR-5 Dominator')
    if jar['zones'] != [1] or jar['verdict'] != 'CANDIDATE' or jar['package'] != '0x10A7605527187EF5':
        raise ValueError('the JAR-5 data changed: %r' % jar)
    zones = zone_comparison(t)
    if zones['entities']['JAR-5 Dominator']['flags']['1'] != zones['entities']['EAT-17 Expendable Anti-Tank']['flags']['3']:
        raise ValueError('the JAR-5 pickup zone flags no longer equal the EAT-17\'s own pickup zone')
    rk = t.component('HellpodRackComponentData')
    byte560 = next(m.describe() for m in rk.members() if m.describe()['offset'] == 560)
    loadout_pod = json.loads(LOADOUT_POD.read_text(encoding='utf-8'))

    exclusive = [r for r in racks if r['exclusiveCarrierRack']]
    return {
        'schemaVersion': 1,
        'build': 'F5FEE03DCFDB',
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'writes': 0,
        'protectionChanges': 0,
        'sources': ['research/pod-payloads-F5FEE03DCFDB.json', 'research/package-residency-F5FEE03DCFDB.json',
            'research/loadout-pod-F5FEE03DCFDB.json', 'research/support-delivery-F5FEE03DCFDB.json',
            'docs/research/runtime-peer-messaging-F5FEE03DCFDB.md (r2/r3 live)', 'domains/package_residency.lua'],
        'pins': pins,
        'pinnedBytesMismatchPerSnapshot': mismatch,
        'interaction': {'jumpTable': '0x%X' % JUMP_TABLE, 'cases': {k: cases[k] for k in sorted(set(
            case_of[v] for v in (1, 2, 3, 13, 14, 29)))}, 'names': names,
            'slotZone': SLOT_ZONE, 'hellpodZone': HELLPOD_ZONE},
        'zoneComparison': zones,
        'hellpodRack': {'slotStride': 64, 'slots': 8, 'item': 0, 'node': 8, 'applyDeltas': 48, 'rackSide': 52,
            'randomPayloadSize': 552, 'spawnPayloadSize': 556,
            'byte560': {'offset': 560, 'storage': byte560['storage'], 'nameLength': byte560['nameLength'],
                'set': sorted(r['path'] or r['resource'] for r in racks if r['byte560'])}},
        'bindManager': {'global': '0x%X' % BIND, 'observations': bind},
        'itemCatalog': catalog,
        'outsideReferences': refs,
        'carrierRacks': {'exclusive': len(exclusive), 'total': len(racks),
            'exclusiveByMaxItems': {str(n): sorted(r['carrier'] for r in exclusive if r['maxItems'] == n)
                for n in sorted({r['maxItems'] for r in exclusive})},
            'racks': racks},
        'loadoutPodFacts': {k: loadout_pod['answers']['q2_fullAutoOneInstance'][k]['label']
            for k in ('privateCopy', 'whoReadsTheModeSet', 'instanceLocal', 'quaternarySlot')},
        'answers': ANSWERS,
        'verdicts': VERDICTS,
        'design': DESIGN,
        'implementation': IMPLEMENTATION,
        'mustNotChange': MUST_NOT_CHANGE,
        'stages': STAGES,
        'refused': REFUSED,
        'open': OPEN,
    }


ANSWERS = {
    'q1_todaysSupportDelivery': {
        'whatIsReplaced': {'label': 'CONFIRMED', 'evidence': 'nothing in any rack: in the carrier beacon\'s first update '
            'its type (element +0xC) becomes the donor\'s (one guarded beacon write, runtime/beacons.lua); the '
            'dispatcher then builds the DONOR\'s pod with the donor\'s rack (payload[2i] -> dispatcher +0x3D8 -> '
            'Transport element +0x0 -> content spawn 0x6D8C30 -> rack creation 0x938A20 -> items 0x934CD0 from the '
            'donor\'s HellpodRack record). The Runtime only captures (support_pods.capture: beacon network id -> pod '
            'block +0x10/+0xC -> Transport +0x8 rack -> slot network ids) and writes each item\'s own copies'},
        'rackRecordWrites': {'label': 'CONFIRMED (live)', 'evidence': 'the separate hd2.fields.payload.entity domain '
            '(domains/pod_payload_writes.lua) writes RackAttach +0 (u64, two aligned dwords in one guarded '
            'transaction) of the TYPE record, after loading the replacement\'s package; live-proven: EAT-700 in the '
            'Stalwart pod slot 2, Grenade Box in the MG-43 pod slot 1 (a pickup with no PickupHellpod zone)'},
        'ownership': {'label': 'CONFIRMED [O]', 'evidence': 'every one of the 56 HellpodRack records has one owner '
            'entity; 6 racks are delivered by two stratagem rows (EAT-17 + Surplus EAT booster, MG-43 + reward, '
            'Resupply + reward, Health Pack Rack pair, Jump Pack pair, Hellbomb pair); every other weapon rack by '
            'exactly one. No support rack resource appears in any of the 270 component tables or anywhere in game.dll '
            '(only the Jammed Pinata rack does). Level / mission scripts in the bundles are not scanned [U]'},
        'lifecycle': {'label': 'CONFIRMED', 'evidence': 'the item references are read only by the spawner, once, '
            'inside the rack\'s creation (0x938B2E -> 0x934CD0, its only caller) on the machine that creates the pod '
            'content; later reads of the record (the rack event 0x935CB0 / 0x934690) take node, offsets and +560, never '
            'the item. A carrier in no loadout has no pod before the first call, so a write at mission start precedes '
            'every read, and a restore at mission end follows the last one; spawned items are standalone entities '
            'afterwards'},
        'restrictionsToday': {'label': 'CONFIRMED', 'evidence': 'all Runtime-side: M.support_delivery (catalog family '
            'support/backpack and a reviewed rack), support_delivery_spec (ONE donor; count must equal the donor '
            'rack\'s; modify for weapons only), the pickup catalogue (primaries and sidearms INCOMPATIBLE, never '
            'offered), the capture\'s expected types (the donor rack\'s). The engine\'s spawner reads no component of '
            'the item: it needs only node != 0 and item != 0 (q2)'},
    },
    'q2_itemKindsInARack': {
        'spawnerTypeAgnostic': {'label': 'CONFIRMED', 'evidence': 'rackSpawner pins: the item resource goes straight '
            'to the networked spawn 0xFDC140; the network id into the slot and the 0x3A listener are generic; '
            'apply_deltas looks the resource up in the loadout item table (customization) or takes the registry '
            'record\'s default deltas'},
        'placement': {'label': 'CONFIRMED', 'evidence': 'rackPlacement pins: node/offset transform for any unit; '
            'PickupHellpod is enabled only on zones of type 13 (an item without one: no change, nothing sent); the bind '
            'record is skipped on a map miss. Vanilla rack items without zone 13 or EntityBind exist: the One True Flag '
            '(zone 3 only), supply boxes, health packs, carry data'},
        'pickupFromRack': {'label': 'STRONG', 'evidence': 'the weapon case 0x97C940 (types 1/2/3 -> slots 1/2/3) ends '
            'in the shared tail 0x97F28A whose 0x3A listener releases the item from its rack (rackLeave pins). The '
            'vanilla CQC-1 One True Flag is a rack item picked up ONLY through that case (zone 3, no PickupHellpod, no '
            'EntityBind) - the exact situation of a racked primary (zone 1). The JAR-5 zone\'s flags equal the EAT-17\'s '
            'own PickupWeaponSupport zone (zoneComparison). Not live-tested for type 1/2'},
        'primarySlot': {'label': 'CONFIRMED', 'evidence': 'PickupWeaponPrimary -> slot 1, PickupWeaponSidearm -> slot 2 '
            '(pickupSlot pins; research loadout-pod)'},
        'primaries': {'label': 'STRONG', 'evidence': 'itemCatalog: every primary (LoadoutEntry item type 1, 56) carries '
            'exactly the PickupWeaponPrimary zone; picking up a world primary is vanilla (a corpse\'s primary stays, research loadout-pod)'},
        'sidearms': {'label': 'PLAUSIBLE', 'evidence': 'only 12 of the 27 item-type-3 entities (sidearms and melee '
            'sidearms) carry a PickupWeaponSidearm zone (the rest have no interaction at all: refused); no vanilla loose sidearm was observed (a corpse\'s '
            'sidearm was gone after reinforce)'},
        'throwables': {'label': 'UNKNOWN (refused)', 'evidence': 'a throwable\'s entity is the live projectile '
            '(Explosive + Throwable on all but the knife); 10 of 23 have no zone at all; PickupThrowable (14) has its '
            'own case (0x97D677, a Throwable-component lookup then 0x9AB950) whose count semantics and whose fuse at '
            'spawn are not traced. A grenade spawned at rest in a pod could arm'},
        'supportWeaponsBackpacks': {'label': 'CONFIRMED', 'evidence': 'vanilla rack items (their own racks); any '
            'catalogued support weapon or backpack into another rack is the live-proven payload.entity pattern '
            '(EAT-700 into the Stalwart pod)'},
        'customizationDeltas': {'label': 'UNKNOWN', 'evidence': 'a weapon slot with apply_deltas = 1 applies the '
            'account\'s customization of that item (0x935966 -> 0x1370420 / 0x878700). For a primary nobody carries, '
            'whether non-default attachments need packages beyond the weapon\'s own loadout package is not traced: '
            'covered by a stage A sub-test'},
    },
    'q3_packages': {
        'whichPackage': {'label': 'STRONG', 'evidence': 'each item\'s own loadout package (packages/generated/loadout/'
            '<name>, via own_loadout_package; JAR-5 0x10A7605527187EF5, P-2 0xBF2250DE0B17285C, G-6 0x7580E5AE368440AE) '
            'from domains/package_residency.lua, keyed player_weapon/<name>, support_weapon/<name>, backpack/<name>, '
            'throwable/<name> (api/assets.lua key_for of the typed handle)'},
        'howRequested': {'label': 'CONFIRMED (live)', 'evidence': 'core/assets.gate: the game\'s RefcountedPackageSystem '
            'request, residency read from the resource manager, kept for the session; live-proven for a player weapon '
            '(LAS-58 Talon), the EAT-700 and the Grenade Box pickups'},
        'rule': {'label': 'design', 'evidence': 'every item package is a declared asset of the definition: requested '
            'at mission start; the carrier rack is written only after all are resident (ASSET_UNAVAILABLE: nothing '
            'written, the definition not callable this mission). The carrier\'s own call-in packages (its rack) are '
            'already loaded by the slot conversion'},
    },
    'q4_instanceModify': {
        'identification': {'label': 'CONFIRMED (code) / live for EAT-17', 'evidence': 'the spawner writes every '
            'spawned item\'s network id into its rack element slot whatever its type (0x935A97), so support_pods.capture '
            '(beacon network id -> pod -> rack -> slot network ids -> entity, entity type checked) identifies a '
            'primary exactly as it identifies the Gas EAT\'s launchers. With no redirect the pod\'s block type and the '
            'rack +0x28 are the CARRIER\'s type'},
        'weaponRecords': {'label': 'CONFIRMED', 'evidence': 'custom_weapons reaches any projectile weapon through its '
            'ProjectileWeapon world record; the JAR-5 has ProjectileWeapon, WeaponMagazine and WeaponData'},
        'fireModes': {'label': 'CONFIRMED (mechanism)', 'evidence': 'research loadout-pod: the WeaponData private copy '
            'through the game\'s 0x75F080 (count 0), then +0x90/+0x94/+0x98 of that copy; the selector reads the '
            'resolved record; at most three modes; a new typed native adapter (stage B)'},
    },
    'q5_multiplayer': {
        'whoSpawnsTheItems': {'label': 'STRONG', 'evidence': 'the machine whose Transport holds the pod (its thrower): '
            'Transport holds local pods only (r3 live: the host\'s pods were not on the client), and the client\'s own '
            'Gas EAT call captured its own rack and launchers (entities 945/946 on the client, picked up by the host). '
            'The spawner reads THAT machine\'s rack record'},
        'whereTheWriteMustBe': {'label': 'STRONG', 'evidence': 'on the caller\'s machine for its own calls; every '
            'compatible machine already derives the same carrier for an id, so each can apply the same mission-scoped '
            'write; the others only receive the replicated items, which need the item packages resident there '
            '(CUSTOM MP ASSETS already requests the synced ids\' assets on every compatible machine)'},
        'vanillaPeers': {'label': 'UNKNOWN (refused)', 'evidence': 'a replicated JAR-5 on a machine without its package '
            'is untested; custom multiplayer is enabled only with every member compatible, but the host also runs its '
            'own calls with vanilla peers present. The new kinds therefore refuse unless the session is solo'},
        'protocol': {'label': 'design', 'evidence': 'no hd2rt/1 change: the items field already carries network ids; '
            'mirroring fire modes later needs only a local rule (each machine copies its own replicated JAR-5), as the '
            'Gas EAT provenance does. Stage MP is not part of A-C'},
    },
}

VERDICTS = [
    {'kind': 'support weapon (the entity its own vanilla rack delivers, 32)', 'verdict': 'SUPPORTED', 'label': 'CONFIRMED',
        'notes': 'vanilla rack items; the live-proven payload.entity pattern; the carrier write is the only new part. '
        'Catalogue variants that no rack delivers (vehicle-mounted, alternates) are not offered'},
    {'kind': 'backpack', 'verdict': 'SUPPORTED', 'label': 'CONFIRMED', 'notes': 'vanilla rack items; no instance '
        'modify (no instance-local backpack field is reviewed)'},
    {'kind': 'primary with a PickupWeaponPrimary zone (all 56)', 'verdict': 'CANDIDATE: stage A live test',
        'label': 'STRONG', 'notes': 'type-agnostic spawner, generic placement and release, One True Flag precedent, '
        'identical zone flags; customization deltas open'},
    {'kind': 'secondary with a PickupWeaponSidearm zone (12 of 27)', 'verdict': 'CANDIDATE after the primary',
        'label': 'PLAUSIBLE', 'notes': 'same case, slot 2; no vanilla loose sidearm observed'},
    {'kind': 'primary/secondary without a pickup zone', 'verdict': 'REFUSED', 'label': 'CONFIRMED',
        'notes': 'nothing could pick it up from the rack'},
    {'kind': 'throwable', 'verdict': 'REFUSED', 'label': 'UNKNOWN', 'notes': 'live explosive entity; count and fuse '
        'semantics not traced'},
    {'kind': 'pickup (supply/ammo/grenade/health box)', 'verdict': 'OUT OF SCOPE here', 'label': 'CONFIRMED',
        'notes': 'already the hd2.pickup catalogue; may be added later through the same item list'},
]

DESIGN = {
    'principle': 'The carrier\'s OWN pod delivers the items: no beacon redirect. At mission start, before the custom '
        'stratagem is callable, the carrier\'s rack record (exclusively the carrier\'s: one record owner, one '
        'consumer row, in no player\'s loadout) gets the authored item references; at mission end its captured bytes '
        'are restored exactly. Nothing is written after a call. Each call\'s items are captured from that call\'s '
        'pod and modified only through game-made private copies.',
    'api': "delivery={family='support', items={{item=hd2.weapon('JAR-5 Dominator'), count=1, "
        "modify={fire_modes={'automatic','single','burst'}}}, {item=hd2.backpack('M-1000 Maxigun Backpack')}}}",
    'schema': [
        'items[k].item (new) XOR items[k].donor (existing): a delivery lists either donors (the existing redirect, '
        'unchanged) or items (the carrier pod); a mix is refused at registration',
        'item: a typed handle only (hd2.weapon for primaries/secondaries, hd2.support_weapon, hd2.backpack); names and '
        'raw resources are refused; the handle\'s entity must be in the generated item catalogue with a supported '
        'verdict (throwables refused with the reason)',
        'count: 1..4 slots of that item (default 1); the total over all items is 1..4 and at most the chosen carrier '
        'rack\'s maxItems (the carrier policy gains this as a hard requirement)',
        'modify: the existing weapon keys (projectile, rpm, spread, ammo, recoil; impact_explosion and rounds for '
        'launchers only) for any delivered projectile weapon; fire_modes (stage B) for weapons whose catalogue entry '
        'is selectable, at most three semantic modes; refused for backpacks',
        'order: items fill the carrier rack\'s vanilla-active slots in order; every other slot with an item is written '
        'empty, so an upgrade-raised count spawns nothing extra',
    ],
    'example': {'id': 'loadout_pod_jar5', 'carrier': "{beacon='support', allow_families={'support','backpack'}}",
        'delivery': "{family='support', items={{item=hd2.weapon('JAR-5 Dominator'), modify={fire_modes="
        "{'automatic','single','burst'}}}, {item=hd2.support_weapon('M-1000 Maxigun')}, "
        "{item=hd2.backpack('M-1000 Maxigun Backpack')}}}",
        'note': 'needs a carrier rack with maxItems >= 3: none on this build (maxItems is 1 or 2); the two-item form '
        '(JAR-5 + Maxigun Backpack, or JAR-5 + a support weapon) fits every two-slot carrier. Three or four items '
        'would need a spawn_payload_size write and unproven slot nodes (a later stage)'},
    'carrierRule': [
        'the carrier is a vanilla support/backpack stratagem that is NOT in any player\'s record this mission, '
        'discovered dynamically, never shared with another custom stratagem and never another definition\'s donor',
        'its rack: record owner count 1, exactly one consumer row (this carrier), random_payload_size 0, every vanilla '
        'item a support weapon or backpack, +560 clear, no reference outside the payload lists, and its current '
        'bytes equal the reviewed vanilla bytes (no other writer owns them)',
        'proved again immediately before the write and before the restore (owner count, consumers from every live '
        'StratagemInfo payload list, the exact slot bytes)',
    ],
}

IMPLEMENTATION = [
    {'step': 1, 'file': 'scripts/generate_carrier_pod_items.py -> domains/carrier_pod_items.lua (new)',
        'what': 'from this research JSON: the item catalogue (resource, kind, verdict, package key, zones) and the '
        'exclusive carrier racks (resource, consumer, active slots, maxItems, vanilla slot bytes)'},
    {'step': 2, 'file': 'runtime/carrier_pod.lua (new; modelled on runtime/carrier_presentation.lua)',
        'what': 'apply(spec): reuse domains/pod_payload_writes capture logic (consumer rows still deliver the rack, the '
        'record identity and owner count, random 0, node != 0) plus a scan proving NO other live StratagemInfo payload '
        'list names the rack; capture all 8 slot items; one guarded transaction writing RackAttach +0 only (two '
        'aligned dwords per slot) for the authored slots and empty for every other slot holding an item; read back; '
        'restore()/restore_now()/finalizer: write the captured bytes back with the written bytes as expectation; '
        'CONFLICT if another writer changed them'},
    {'step': 3, 'file': 'runtime/carrier_allocator.lua',
        'what': 'allocate_policies: a definition with pod_items = n accepts only candidates whose rack is an '
        'exclusive carrier rack with maxItems >= n (domains/carrier_pod_items.lua); reason logged per candidate. '
        'Unchanged for every other definition'},
    {'step': 4, 'file': 'runtime/custom_stratagems.lua',
        'what': 'support_delivery_spec: accept items[k].item (typed handle), build {kind=\'support\', mode=\'carrier_pod\', '
        'items by entity type, slot layout, modify per item, assets = the item packages}; decide(): for carrier_pod '
        'return a no-write change (the carrier delivers itself); start_capture(): spec.type = the carrier type, '
        'item_types = the authored types, then check slot k holds authored type k; advance(): a new state between the '
        'assets and the slot conversion applies runtime/carrier_pod; restore_all()/mission_end(): restore it; '
        'payload_signature(): a new branch only for carrier_pod (existing strings unchanged); M.mirrored(): false for '
        'carrier_pod; colour_donor(): unchanged fallback'},
    {'step': 5, 'file': 'runtime/multiplayer.lua',
        'what': 'client_family(d) returns nil for carrier_pod (a client refuses its call); the carrier pod applies only '
        'with one player in the session (host_guard), so a host with peers refuses the definition for the mission'},
    {'step': 6, 'file': 'runtime/custom_weapons.lua (+ a typed native adapter)',
        'what': 'stage B: fire_modes through the WeaponData copy routine 0x75F080 (entry-byte proof like '
        'native_weapon_copy), guards: the call\'s associated entity, the copy\'s modes equal the type\'s before, '
        'the type record unchanged after'},
    {'step': 7, 'file': 'scripts/generate_custom_stratagem_schema.py, sdk validator, docs/custom-stratagem-api.md',
        'what': 'schema for items[k].item / count / modify.fire_modes; the builder\'s typed item references'},
    {'step': 8, 'file': 'tests (new)', 'what': 'offline: the transaction bytes on a snapshot overlay; the restore '
        'byte-for-byte; a refused carrier (shared rack, in a loadout, another writer); a vanilla call of every other '
        'support stratagem unchanged; r3/r4 registry hashes of the existing examples unchanged'},
]

MUST_NOT_CHANGE = [
    'the existing donor delivery (items[k].donor and {stratagem=...}): its beacon redirect, capture, Gas EAT binding '
        'and provenance publication, byte for byte',
    'payload_signature / registry_hash for every existing definition (r3 GasEat and r4 examples must keep agreeing)',
    'runtime/peer_protocol.lua grammar, custom_mp_items acceptance rules, CLIENT_FAMILIES membership',
    'support_pods.capture API and behaviour (the new path only passes another type)',
    'the public hd2.fields.payload.entity domain and the hd2.pickup catalogue (no primary is offered there)',
]

STAGES = [
    {'stage': 'A', 'title': 'A primary in the carrier pod, and its pickup',
        'build': 'domains/carrier_pod_items.lua, runtime/carrier_pod.lua, the allocator requirement, the spec and '
        'decide/capture changes; an example with items={{item=hd2.weapon(\'JAR-5 Dominator\')}} (one slot, any '
        'exclusive one-slot carrier)',
        'liveTest': 'solo host. At mission start: CARRIER POD APPLIED (rack, slots, before/after bytes, the JAR-5 '
        'package resident). Call: the carrier\'s blue beam and pod; the pod opens with a JAR-5 on the rack; it is '
        'interactable; pick-up puts it in the primary slot (the old primary drops); it fires and reloads; a second '
        'call delivers a second JAR-5. Sub-test: the account\'s JAR-5 customized (non-default attachments) and not '
        'equipped. Control: a vanilla support call of another stratagem unchanged. Back aboard the ship: CARRIER POD '
        'RESTORED (exact bytes)',
        'logs': ['CARRIER POD APPLIED', 'DELIVERED: pod P, rack R: weapon E (JAR-5, network id N)',
            'the inventory slot after the pickup', 'CARRIER POD RESTORED: exact'],
        'refuseIf': 'not solo; package not resident; carrier rack not exclusive or not vanilla; any guard'},
    {'stage': 'B', 'title': 'Full-auto on that one delivered JAR-5',
        'build': 'the WeaponData copy adapter (0x75F080, count 0) and the fire_modes write on the captured entity',
        'liveTest': 'the delivered JAR-5 cycles single/burst/automatic; an equipped or another JAR-5 keeps '
        'single/burst; the type record unchanged (logged)', 'logs': ['CONFIGURED fire modes ... type modes unchanged']},
    {'stage': 'C', 'title': 'Mixed pod contents',
        'build': 'two items on a two-slot exclusive carrier: a primary and a support weapon or backpack',
        'liveTest': 'both items spawn on the rack, each picks up into its own slot, the capture names both, per-item '
        'modify applies only to its item'},
    {'stage': 'D (later)', 'title': 'Secondaries; three or four items (spawn_payload_size and node proof)'},
    {'stage': 'MP (later)', 'title': 'Several compatible Runtimes', 'build': 'each machine applies the same carrier '
        'pod write; item assets on every compatible machine; fire-mode copies mirrored by network id through the '
        'existing items field (no grammar change); vanilla peers keep the definition refused'},
]

REFUSED = [
    {'request': 'throwables in a pod', 'reason': 'the entity is the live explosive; PickupThrowable count and fuse '
        'semantics are not traced'},
    {'request': 'primaries or secondaries without their slot\'s pickup zone', 'reason': 'nothing could pick them up'},
    {'request': 'a carrier whose rack is shared (EAT-17, MG-43, Jump Pack, Hellbomb, Resupply, Health Pack) or '
        'read-only', 'reason': 'not exclusively the carrier\'s record'},
    {'request': 'writing a donor\'s rack, or any rack of a stratagem someone carries', 'reason': 'a vanilla call would '
        'change'},
    {'request': 'more items than the carrier rack\'s vanilla active slots', 'reason': 'spawn_payload_size and the '
        'extra slot nodes are not proven for this use'},
    {'request': 'writing the rack after the first call of the mission', 'reason': 'carrier rule'},
    {'request': 'multiplayer for the new kinds in stages A-C', 'reason': 'replication to machines without the item '
        'package is unproven'},
]

OPEN = [
    'customization deltas (apply_deltas) on an uncarried primary: do non-default attachments need other packages?',
    'level or mission scripts spawning a support rack by name (bundles are not scanned)',
    'the network owner of a picked-up weapon (decides who replicates its fire mode)',
    'record +560 (UINT8, hidden name 27) and zone +45 (UINT8, hidden name 13): unnamed; not written',
    'the bind manager 0x33267F8 is empty in every retained snapshot (no rack was captured in them)',
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
            print('research/carrier-pod-items-F5FEE03DCFDB.json is stale')
            return 1
        print('research/carrier-pod-items-F5FEE03DCFDB.json is current')
        return 0
    OUTPUT.write_text(text, encoding='utf-8')
    print('wrote', OUTPUT.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
