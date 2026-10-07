"""Which support weapons are EXPENDABLE (a disposable, non-reloadable lifecycle), and which of them can carry a clone of
which donor? (research/docs/expendable-carriers-F5FEE03DCFDB.md). Read-only, offline.

"Expendable" is the weapon's LIFECYCLE, never its vanilla round count: the weapon discards itself when empty and can
never be reloaded. Membership is derived from game data and code, never from names. Two separate questions:

* LIFECYCLE MEMBER (the expendable group's pool of weapon types): WeaponData +0x1CC auto_drop_ability set, played by the
  out-of-ammo handler 0x753A10 only when the weapon has no instance in either gate manager: gate 1 the WeaponReload
  manager (component world +0x7571C8), gate 2 the SeatCollection manager (component world +0xEEF730: its update 0x633E80
  walks its instance handles and resolves each through 0x510E60, the SeatCollection type-table reader, slot 0xF12D68 =
  component index 286). A component manager holds instances only for entities whose TYPE has that component, so a
  type without WeaponReload and SeatCollection is never reloaded and always discards itself. Also checked: no
  WeaponRounds / WeaponAssistedReload / WeaponLinkedAmmo feed, a WeaponMagazine with no spare magazines.
* CLONE COMPATIBILITY for a donor (the type-level clone of runtime/weapon_clone.lua): the carrier's component SET must
  equal the donor's (components are fixed per type: an extra component keeps its behaviour, a missing one cannot be
  supplied), the expendable contract members (policy 'identical' in scripts/research_carrier_weapon_clone.py) must
  already be equal, and every written record must have one owner.

Proves on build F5FEE03DCFDB, from the pinned entity tables, the game.dll image, the seven retained snapshots and the
rack research (research/carrier-pod-nodes, pod-payloads):

1. The 27 support weapons hold exactly five lifecycle members: EAT-17 (lat_oneshot), EAT-700
   (expendable_napalm_launcher), EAT-411 (expendable_massive_rocket_launcher), MLS-4X Commando
   (laser_guided_missile_launcher) and MGX-42 Bullet Storm (expendable_machinegun; native stratagem type
   Expendable_Machinegun, stable id 3288352984). Outside the 27 only two types carry an auto-drop ability, neither a
   carrier: a second, unnamed EAT-17 type (no stratagem row) and the MS-11 Solo Silo remote (no projectile, no
   magazine).
2. Their clone classes: {EAT-17, EAT-700, EAT-411}; {MLS-4X} alone (EAT-17 + Faction, GuidanceTarget, LaserDesignator,
   SensorEye, WeaponLinker; Backblast, DropMode and magazine contract differ); {MGX-42} alone (EAT-17 - Backblast;
   EquipmentType, auto-drop ability 97, magazine contract differ). So the EAT-17's clone carriers stay EAT-700, EAT-411.
3. Magazines: EATs 1 round, 0 spare, not chambered; Commando 4 rounds, 0 spare, not chambered; Bullet Storm 300
   rounds, 0 spare, chambered, a tracer pattern (Type 1).
4. Pods: EAT-700 and MGX-42 two launchers at nodes 47 / 48, sides 2 / 1 (the EAT-17's own layout); EAT-411 one, a
   second usable at attach_1 (node 17, side 1); Commando one (spawn count 1).
5. A round-count override: the clone mechanism writes no WeaponMagazine member (type level: refused); the only private
   path is the existing instance-local `ammo` (runtime/custom_weapons.lua: the entity's own magazine copy through the
   game's copy routine 0x770B10), not part of the clone and not live-tested on a support weapon.

Output: research/expendable-carriers-F5FEE03DCFDB.json. Nothing is written to the game.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from capstone import x86  # noqa: E402

import research_carrier_weapon_clone as clone  # noqa: E402
from research_carrier_weapon_clone import base, SNAPSHOTS, DONOR, slot_of, hexid  # noqa: E402
from scan import golib, tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/expendable-carriers-F5FEE03DCFDB.json'
NODES = ROOT / 'research/carrier-pod-nodes-F5FEE03DCFDB.json'
POD_PAYLOADS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
PRESENTATION = clone.PRESENTATION
SLOT_BASE = clone.SLOT_BASE
GATE_MANAGERS = {'WeaponReloadComponentData': (0x3326A70, 0x7571C8), 'SeatCollectionComponentData': (0x3326D88, 0xEEF730)}
NO_FEED = ('WeaponRoundsComponentData', 'WeaponAssistedReloadComponentData', 'WeaponLinkedAmmoComponentData')
MAGAZINE_COPY = 0x770B10          # the game's per-entity WeaponMagazine copy routine (runtime/custom_weapons.lua ammo)
CLONE_COMPONENTS = clone.DOMAIN_COMPONENTS   # what runtime/weapon_clone.lua writes (WeaponMagazine is not among them)
NAME_SEARCH = ('bulletstorm', 'bullet_storm', 'bullet storm', 'expendable', 'oneshot', 'disposable', 'commando', 'mls',
    'laser_guided', 'machinegun')
FOCUS = ['EAT-17 Expendable Anti-Tank', 'EAT-700 Expendable Napalm', 'EAT-411 Leveller', 'MLS-4X Commando',
    'MGX-42 Bullet Storm']

PINS = {
    # Gate 2 of the out-of-ammo handler is the SeatCollection manager.
    'seatGate': [
        (0x753BD5, 'mov rax, qword ptr [rip + 0x2bd31ac]', 0x3326D88, 'out-of-ammo handler gate 2: the manager in '
            'G+0x3326D88 ...'),
        (0x753C09, 'mov eax, dword ptr [r10 + rdx*8]', None, '... its entity hash map (+0x20 slots, +0x28 capacity) ...'),
        (0x753C23, 'cmp dword ptr [r10 + rdx*8 + 4], -1', None, '... has the weapon entity an instance there ...'),
        (0x753C29, 'jne 0x753d89', None, '... then NO auto drop'),
        (0x56915A, 'lea rax, [rbx + 0xeef730]', None, 'the manager globals: component world +0xEEF730 ...'),
        (0x569161, 'mov qword ptr [rip + 0x2dbdc20], rax', 0x3326D88, '... is G+0x3326D88'),
        (0x573A84, 'lea rcx, [rdi + 0xeef730]', None, 'the world update passes that manager ...'),
        (0x573A8E, 'call 0x633e80', None, '... to its update 0x633E80 ...'),
        (0x633EC0, 'mov rbx, qword ptr [r14 + 0x38]', None, '... which walks its instance handles (+0x38) ...'),
        (0x633ED3, 'call 0x510e60', None, '... resolving each handle through 0x510E60 ...'),
        (0x510E81, 'mov r11, qword ptr [rax + 0xf12d68]', None, '... the SeatCollection type table (entity manager '
            '+0xF12D68 = slot of component index 286)'),
    ],
    # The per-entity magazine copy the instance-local ammo override uses.
    'magazineCopy': [
        (0x57417F, 'call 0x770b10', None, 'the entity-delta dispatcher\'s WeaponMagazine case: the copy routine'),
    ],
}


def magazine(t: tables.EntityTables, resource: int) -> dict | None:
    wm = t.component('WeaponMagazineComponentData')
    record = wm.record_of(resource)
    if record is None:
        return None
    raw = wm.raw(record)
    pattern = list(struct.unpack_from('<32I', raw, 4))
    length = next((i for i, v in enumerate(pattern) if v == 0), 32)
    return {'record': record, 'owners': len(wm.owners(record)),
        'type': struct.unpack_from('<I', raw, 0)[0], 'pattern': pattern[:length],
        'firstProjectile': struct.unpack_from('<I', raw, 0x84)[0],
        'capacity': struct.unpack_from('<I', raw, 0x88)[0], 'magazines': struct.unpack_from('<I', raw, 0x8C)[0],
        'magazinesRefill': struct.unpack_from('<I', raw, 0x90)[0],
        'magazinesMax': struct.unpack_from('<I', raw, 0x94)[0],
        'reloadThreshold': struct.unpack_from('<I', raw, 0x98)[0], 'chambered': raw[0x9C],
        'fields': 'WeaponMagazine +0 Type, +4 Pattern[32], +0x84 FirstProjectile, +0x88 Capacity, +0x8C Magazines, '
            '+0x90 MagazinesRefill, +0x94 MagazinesMax, +0x98 ReloadThreshold, +0x9C Chambered (Filediver leads, '
            'decoded from the pinned record)'}


def u32_of(t, resource, component, offset):
    comp = t.component(component)
    record = comp.record_of(resource)
    return None if record is None else struct.unpack_from('<I', comp.raw(record), offset)[0]


def slot_reads(image: xref.CodeImage, t: tables.EntityTables, function: int, depth: int = 1, seen=None) -> list[str]:
    """Component type tables a function (and its direct callees, to depth) reads by slot displacement."""
    seen = set() if seen is None else seen
    if function in seen:
        return []
    seen.add(function)
    t.entity_rows()
    names = {k: t.type_name(v) for k, v in t._index_type.items()}  # noqa: SLF001 - research access
    out = []
    for ins in image.function_insns(function):
        for op in ins.operands:
            if op.type == x86.X86_OP_MEM and SLOT_BASE <= op.mem.disp < SLOT_BASE + 8 * 1024 \
                    and (op.mem.disp - SLOT_BASE) % 8 == 0:
                name = names.get((op.mem.disp - SLOT_BASE) // 8)
                if name:
                    out.append(name)
        if depth > 0 and ins.mnemonic == 'call' and ins.operands[0].type == x86.X86_OP_IMM:
            out += slot_reads(image, t, ins.operands[0].imm, depth - 1, seen)
    return sorted(set(out))


def prove_pins(image: xref.CodeImage) -> dict:
    out = {}
    for group, rows in list(PINS.items()) + [('autoDrop', clone.PINS['autoDrop'])]:
        out[group] = []
        for rva, asm, target, role in rows:
            pin = image.pin(rva, role, asm)
            if target is not None and pin.get('ripTarget') != target:
                raise ValueError('pin %x: rip target %r, expected %x' % (rva, pin.get('ripTarget'), target))
            out[group].append(pin)
    return out


def gate_components(image: xref.CodeImage, t: tables.EntityTables) -> dict:
    """Which component each gate manager is: the type table its routines read."""
    seat = slot_reads(image, t, 0x633E80, 1)
    reload_copy = slot_reads(image, t, 0x779410, 0)
    mag_copy = slot_reads(image, t, MAGAZINE_COPY, 1)
    if 'SeatCollectionComponentData' not in seat or 'WeaponReloadComponentData' not in reload_copy:
        raise ValueError('gate managers not identified: %r %r' % (seat, reload_copy))
    if 'WeaponMagazineComponentData' not in mag_copy:
        raise ValueError('0x770B10 does not read the WeaponMagazine type table: %r' % mag_copy)
    if slot_of(t, 'SeatCollectionComponentData') != 0xF12D68:
        raise ValueError('SeatCollection slot moved')
    return {'gate1': {'manager': 'component world +0x7571C8 (G+0x3326A70)', 'component': 'WeaponReloadComponentData',
            'evidence': 'its delta copy routine 0x779410 (dispatcher case 0x574C42) reads %s' % reload_copy},
        'gate2': {'manager': 'component world +0xEEF730 (G+0x3326D88)', 'component': 'SeatCollectionComponentData',
            'evidence': 'its update 0x633E80 (called with it at 0x573A8E) resolves every instance handle through '
                '0x510E60, which reads %s' % seat},
        'magazineCopy': {'routine': '0x%X' % MAGAZINE_COPY, 'reads': mag_copy},
        'rule': 'a component manager holds an instance only for an entity whose TYPE has that component (the '
            'component set is fixed per type: research_carrier_weapon_clone), so a type without WeaponReload and '
            'SeatCollection passes both gates on every entity'}


def name_search(t: tables.EntityTables) -> dict:
    labels = {t.label(r) for r in t.resources()}
    out = {}
    for needle in NAME_SEARCH:
        paths = sorted({p for p in t.paths.values() if needle in p.lower()})
        out[needle] = {'entityLabels': sorted(x for x in labels if needle in x.lower()),
            'resourceNames': len(paths),
            'supportWeaponOrRackNames': [p for p in paths if '/support_weapons/' in p and p.count('/') == 5
                or '/weapon_rack/' in p]}
    return out


def auto_drop_census(t: tables.EntityTables, weapons: set, payloads: dict) -> dict:
    """Every entity type with WeaponData whose +0x1CC is set, with what it is (the pod-payload item catalogue)."""
    wd, uc = t.component('WeaponDataComponentData'), t.component('UnitComponentData')
    items = {}

    def walk(o):
        if isinstance(o, dict):
            if 'category' in o and 'resource' in o and 'standalonePickup' in o:
                items.setdefault(o['resource'], o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(payloads)
    out = {}
    for r in t.with_component('WeaponDataComponentData'):
        value = struct.unpack_from('<I', wd.raw(wd.record_of(r)), 0x1CC)[0]
        if not value:
            continue
        comps = t.entity(r)
        unit = uc.record_of(r)
        item = items.get(hexid(r), {})
        out[t.label(r)] = {'autoDropAbility': value, 'supportWeapon': r in weapons,
            'unit': t.paths.get(struct.unpack_from('<Q', uc.raw(unit), 0)[0]) if unit is not None else None,
            'projectileWeapon': 'ProjectileWeaponComponentData' in comps,
            'weaponMagazine': 'WeaponMagazineComponentData' in comps,
            'weaponReload': 'WeaponReloadComponentData' in comps,
            'catalogueName': item.get('name'), 'rackPayloadOf': item.get('vanillaRackPaths'),
            'standalonePickup': item.get('standalonePickup')}
    return out


def rack_facts(nodes: dict, payloads: dict) -> dict:
    ident = {r['resource']: r for r in payloads['racks']}
    out = {}
    for r in nodes['racks']:
        for name in r['consumers']:
            if name not in FOCUS:
                continue
            i = ident[r['resource']]
            out[name] = {'rack': r['path'], 'resource': r['resource'], 'exclusiveCarrierRack': r['exclusiveCarrierRack'],
                'consumers': [{'name': c['name'], 'stableId': c['id'], 'nativeType': c['nativeType']}
                    for c in i['consumers']],
                'recordOwnerCount': i['ownerCount'], 'randomPayloadSize': r['randomPayloadSize'],
                'spawnPayloadSize': r['spawnPayloadSize'], 'capacity': r['capacity'], 'usableSlots': r['usableSlots'],
                'vanillaPopulated': r['vanillaPopulated'],
                'slots': [{'index': s['index'], 'item': s['item'], 'node': s['node']['index'],
                    'nodeName': s['node']['name'], 'rackSide': s['rackSide'], 'insideSpawnCount': s['insideSpawnCount'],
                    'usable': s['usable']} for s in r['slots'] if s['item'] or s['usable']]}
    return out


def pod_verdict(rack: dict, reference: dict) -> dict:
    usable = [s for s in rack['slots'] if s['usable']]
    ref = [(s['node'], s['rackSide']) for s in reference['slots'] if s['usable']]
    layout = [(s['node'], s['rackSide']) for s in usable]
    two_clean = len(usable) >= 2 and layout[:2] == ref[:2]
    out = {'one': 'CLEAN (slot 0: node %d, side %d, the EAT-17 rack\'s own slot 0)' % layout[0]
            if layout and layout[0] == ref[0] else 'slot 0 differs from the EAT-17 rack',
        'two': None}
    if len(usable) < 2:
        extra = [s for s in rack['slots'] if s['item'] and not s['insideSpawnCount']]
        out['two'] = ('REFUSED: capacity %d (spawn count %d); %s' % (rack['capacity'], rack['spawnPayloadSize'],
            'slot %d holds a vanilla item at node %d, side %d OUTSIDE the spawn count, and the spawn count is never '
            'written (runtime/carrier_pod.lua)' % (extra[0]['index'], extra[0]['node'], extra[0]['rackSide'])
            if extra else 'no second usable slot'))
    elif two_clean:
        out['two'] = 'CLEAN (slots 0 / 1 at nodes %d / %d, sides %d / %d: the EAT-17 rack\'s own layout)' % (
            layout[0][0], layout[1][0], layout[0][1], layout[1][1])
    else:
        s = usable[1]
        out['two'] = ('POSSIBLE, not identical to the EAT-17 layout: slot %d is %s at node %d (%s), side %d, where the '
            'EAT-17 rack uses node %d; live 2026-10-05: both pod sides open but the second launcher sits on the same '
            'physical side' % (s['index'], 'EMPTY' if not s['item'] else 'filled', s['node'], s['nodeName'],
            s['rackSide'], ref[1][0]))
    return out


def weapon_facts(t, go, name, resource, weapons, names, classes, racks, presentation):
    comps = set(t.entity(resource))
    donor = set(t.entity(DONOR))
    mag = magazine(t, resource)
    auto = u32_of(t, resource, 'WeaponDataComponentData', 0x1CC)
    drop_mode = struct.unpack_from('<i', struct.pack('<I', u32_of(t, resource, 'EquipmentComponentData', 0x88)))[0]
    owners = {}
    for component, record in sorted(t.entity(resource).items()):
        owners[component] = len(t.component(component).owners(record))
    shared = sorted(c for c, n in owners.items() if n != 1)
    gates = {c: c in comps for c in GATE_MANAGERS}
    feeds = {c: c in comps for c in NO_FEED}
    member = bool(auto) and not any(gates.values()) and not any(feeds.values()) and mag is not None and \
        mag['magazines'] == 0 and mag['magazinesMax'] == 0
    cls = next(sorted(c) for c in classes if name in c)
    diff = clone.member_diff(t, go, DONOR, resource) if resource != DONOR else {'members': [], 'owners': {}}
    contract = [{'member': m['component'].replace('ComponentData', '') + ' ' + m['offset'], 'role': m['role'],
        'donor': m['donor'], 'carrier': m['carrier']} for m in diff['members'] if m['policy'] == 'identical']
    missing, extra = sorted(donor - comps), sorted(comps - donor)
    written = [c for c in CLONE_COMPONENTS if c in comps]
    exclusive = all(owners[c] == 1 for c in written)
    p = presentation.get(t.label(resource), {})
    rack = racks.get(name)
    why = []
    if missing or extra:
        why.append('its component set differs from the EAT-17\'s (%s)' % '; '.join(
            x for x in ('missing ' + ', '.join(c.replace('ComponentData', '') for c in missing) if missing else '',
            'extra ' + ', '.join(c.replace('ComponentData', '') for c in extra) if extra else '') if x))
    if contract:
        why.append('its expendable contract differs (%s)' % ', '.join(c['member'] for c in contract))
    if not exclusive:
        why.append('a written record is shared')
    if p.get('inWorldLoot') or p.get('deliveredBy') != [name]:
        why.append('in world loot or delivered by another row')
    if resource == DONOR:
        compat = {'compatible': False, 'reason': 'the donor itself (its rack is shared with the LATOneshot_Booster row)'}
    elif why:
        compat = {'compatible': False, 'reason': '; '.join(why)}
    else:
        compat = {'compatible': True, 'reason': 'the EAT-17\'s component set, its expendable contract identical, every '
            'written record exclusively owned, delivered only by its own rack, in no loot table'}
    return {
        'name': name, 'entity': t.label(resource), 'resource': hexid(resource),
        'stratagem': rack and next((c for c in rack['consumers'] if c['name'] == name), None),
        'reload': {'WeaponReload': gates['WeaponReloadComponentData'], 'SeatCollection':
            gates['SeatCollectionComponentData'], **{c.replace('ComponentData', ''): v for c, v in feeds.items()},
            'reloadable': gates['WeaponReloadComponentData'] or any(feeds.values())},
        'lifecycle': {'autoDropAbility': auto, 'dropMode': drop_mode,
            'pickupDropAbility': u32_of(t, resource, 'EquipmentComponentData', 0xB8),
            'infiniteAmmo': u32_of(t, resource, 'WeaponDataComponentData', 0x3B8),
            'equipmentType': u32_of(t, resource, 'EquipmentComponentData', 0x80),
            'backblast': 'BackblastComponentData' in comps},
        'magazine': mag,
        'projectile': u32_of(t, resource, 'ProjectileWeaponComponentData', 0),
        'ownership': {'recordOwners': owners, 'sharedRecords': shared, 'cloneWrittenRecordsExclusive': exclusive,
            'inWorldLoot': p.get('inWorldLoot'), 'deliveredBy': p.get('deliveredBy')},
        'pod': rack,
        'componentSet': {'count': len(comps), 'cloneClass': cls, 'missingVsEat17': missing, 'extraVsEat17': extra},
        'eat17Contract': contract,
        'expendableMember': member,
        'eat17Clone': compat,
    }


def snapshot_facts(t: tables.EntityTables) -> dict:
    out = {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            world = mem.ptr(mem.game + clone.WEAPON_DATA_MANAGER_GLOBAL) - clone.WEAPON_DATA_MANAGER
            gates = {c: mem.ptr(mem.game + g) - world == m for c, (g, m) in GATE_MANAGERS.items()}
            em = mem.ptr(mem.game + clone.ENTITY_MANAGER)
            in_place = {c: mem.read(mem.ptr(em + slot_of(t, c)), len(t.component(c).body)) == t.component(c).body
                for c in ('WeaponMagazineComponentData', 'WeaponDataComponentData', 'EquipmentComponentData')}
            out[name] = {'gateManagersAtTheirOffsets': gates, 'typeTablesAsPinned': in_place}
        finally:
            mem.close()
    return out


def main():
    t = tables.pinned()
    go = golib.default_library()
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = prove_pins(image)
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    gates = gate_components(image, t)
    names = clone.names_by_path()
    weapons = t.find('equipment/support_weapons/')
    sets = {}
    for r in weapons:
        sets.setdefault(frozenset(t.entity(r)), []).append(names.get(t.label(r), t.label(r)))
    classes = [sorted(v) for v in sets.values()]
    presentation = {c['weapon']: c for c in json.loads(PRESENTATION.read_text(encoding='utf-8'))['carrierCandidates']}
    racks = rack_facts(json.loads(NODES.read_text(encoding='utf-8')), json.loads(POD_PAYLOADS.read_text(
        encoding='utf-8')))
    by_name = {names.get(t.label(r), t.label(r)): r for r in weapons}
    every = {n: weapon_facts(t, go, n, r, set(weapons), names, classes, racks, presentation)
        for n, r in sorted(by_name.items())}
    members = [n for n in FOCUS if every[n]['expendableMember']]
    derived = sorted(n for n, f in every.items() if f['expendableMember'])
    if sorted(members) != derived:
        raise ValueError('lifecycle members outside the reviewed focus: %r' % derived)
    compat = [n for n in FOCUS if every[n]['eat17Clone']['compatible']]
    hosts = json.loads(clone.OUTPUT.read_text(encoding='utf-8'))['checks']['eat17CloneHosts']
    if compat != hosts:
        raise ValueError('EAT-17 clone carriers %r differ from the carrier weapon clone research %r' % (compat, hosts))
    reference = racks['EAT-17 Expendable Anti-Tank']
    for n in FOCUS:
        every[n]['podVerdict'] = pod_verdict(racks[n], reference)
        every[n]['overrides'] = override_verdicts(every[n])
    census = auto_drop_census(t, set(weapons), json.loads(POD_PAYLOADS.read_text(encoding='utf-8')))
    outside = {k: v for k, v in census.items() if not v['supportWeapon']}
    # The two auto-drop types outside the 27 are no carrier candidates: a second, unnamed EAT-17 type (the EAT-17
    # unit and package, a standalone pickup no stratagem row delivers) and the MS-11 Solo Silo's remote (no
    # ProjectileWeapon, no WeaponMagazine: a rack item of the Solo Silo's own pod).
    for k, v in outside.items():
        if v['catalogueName'] == 'EAT-17 Expendable Anti-Tank':
            v['role'] = 'a second EAT-17 type (no stratagem row of its own: never a carrier weapon)'
        elif v['rackPayloadOf'] == ['content/fac_helldivers/hellpod/weapon_rack/weapon_rack_mini_missile_silo'] \
                and not v['projectileWeapon']:
            v['role'] = 'the MS-11 Solo Silo remote (no projectile, no magazine: not a weapon a clone can use)'
        else:
            raise ValueError('an unreviewed auto-drop type: %s %r' % (k, v))
    snaps = snapshot_facts(t)
    checks = {
        'lifecycleMembers': members,
        'lifecycleMembersDerivedFromAll27': derived,
        'eat17CloneCompatible': compat,
        'cloneClasses': {n: every[n]['componentSet']['cloneClass'] for n in FOCUS},
        'autoDropWeapons': {k: v['autoDropAbility'] for k, v in census.items()},
        'autoDropOutsideThe27': {k: v['role'] for k, v in outside.items()},
        'noMemberHasAGateComponent': all(not every[n]['reload']['WeaponReload'] and not every[n]['reload'][
            'SeatCollection'] for n in members),
        'noSupportWeaponHasSeatCollection': not any(every[n]['reload']['SeatCollection'] for n in every),
        'gateManagersInEverySnapshot': all(all(v['gateManagersAtTheirOffsets'].values()) for v in snaps.values()),
        'typeTablesAsPinnedInEverySnapshot': all(all(v['typeTablesAsPinned'].values()) for v in snaps.values()),
        'membersEveryRecordExclusive': {n: not every[n]['ownership']['sharedRecords'] for n in members},
        'podCapacity': {n: racks[n]['capacity'] for n in FOCUS},
    }
    result = {
        'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'gates': gates,
        'nameSearch': name_search(t),
        'autoDropCensus': census,
        'cloneClasses': sorted(classes, key=lambda c: (-len(c), c)),
        'weapons': {n: every[n] for n in FOCUS},
        'otherSupportWeapons': {n: {'expendableMember': f['expendableMember'], 'autoDropAbility': f['lifecycle'][
            'autoDropAbility'], 'reloadable': f['reload']['reloadable'], 'cloneClass': f['componentSet']['cloneClass']}
            for n, f in every.items() if n not in FOCUS},
        'snapshots': snaps,
        'checks': checks,
        'domain': domain(every, members),
        'verdicts': VERDICTS,
    }
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; members', members, '; EAT-17 clone carriers',
        compat, '; checks', {k: v for k, v in checks.items() if k not in ('autoDropWeapons', 'cloneClasses')})


def override_verdicts(f: dict) -> dict:
    mag = f['magazine']
    return {
        'roundsTypeLevel': {'possible': False, 'status': 'REFUSED',
            'reason': 'the clone writes only %s; every WeaponMagazine member is policy identical (never written) and '
                'no consumer proof exists for when the game reads the type Capacity (+0x88)' % ', '.join(
                    c.replace('ComponentData', '') for c in CLONE_COMPONENTS)},
        'roundsInstanceLevel': {'possible': mag is not None, 'status': 'HYPOTHESIS',
            'path': 'the ammo key of a delivered weapon\'s modify (runtime/custom_weapons.lua): that entity\'s own '
                'magazine copy (game routine 0x770B10) capacity and round counts; the type record is untouched',
            'vanilla': mag and mag['capacity'],
            'reason': 'the mechanism is live only on the Pelican chin turret (raising a Gatling magazine); reducing a '
                'disposable support weapon to 1 round, and the auto drop after that round, are not live-tested'},
        'projectileInstanceLevel': {'possible': f['projectile'] is not None, 'status': 'HYPOTHESIS',
            'path': 'the projectile / impact_explosion keys of a delivered weapon\'s modify (that entity\'s own '
                'ProjectileWeapon copy, routine 0x61AF10)' + ('; a pattern magazine (Type 1) gets its pattern off on its own copy'
                    if mag and mag['type'] == 1 else ''),
            'reason': 'instance-local and reviewed for support weapons; on this weapon type not live-tested'
                if f['name'] not in ('EAT-17 Expendable Anti-Tank', 'EAT-700 Expendable Napalm', 'EAT-411 Leveller')
                else 'the clone fires the donor\'s round at level full; impact_explosion live-proven on the EAT-17G '
                    '(Gas EAT)'},
    }


def domain(every: dict, members: list) -> dict:
    """What domains/weapon_clone.lua gets (scripts/generate_weapon_clone.py): the lifecycle members in order, each with
    its clone class, pod capacity, magazine and per-donor clone compatibility."""
    out = {'order': members, 'members': {}}
    for n in members:
        f = every[n]
        out['members'][n] = {'entity': f['resource'], 'label': f['entity'],
            'stableId': f['stratagem'] and f['stratagem']['stableId'],
            'autoDropAbility': f['lifecycle']['autoDropAbility'], 'dropMode': f['lifecycle']['dropMode'],
            'rounds': f['magazine']['capacity'], 'spareMagazines': f['magazine']['magazinesMax'],
            'chambered': f['magazine']['chambered'] == 1, 'podCapacity': f['pod']['capacity'],
            'exclusiveRack': f['pod']['exclusiveCarrierRack'],
            'cloneClass': [x for x in members if x in f['componentSet']['cloneClass']],
            'roundsOverride': {'type': False, 'instance': f['magazine'] is not None},
            'clone': {'EAT-17 Expendable Anti-Tank': {'compatible': f['eat17Clone']['compatible'],
                'reason': f['eat17Clone']['reason']}}}
    return out


VERDICTS = {
    'principle': 'expendable = the weapon\'s lifecycle (auto drop when empty, never reloadable), derived from data; a '
        'lifecycle member is a valid carrier for a donor\'s type-level clone only inside the donor\'s component class',
    'EAT-17 Expendable Anti-Tank': 'MEMBER (the donor); not a carrier: its rack is shared with the LATOneshot_Booster '
        'row (two consumers)',
    'EAT-700 Expendable Napalm': 'MEMBER; EAT-17 clone carrier (first)',
    'EAT-411 Leveller': 'MEMBER; EAT-17 clone carrier (second; a second pod item sits at attach_1)',
    'MLS-4X Commando': 'MEMBER (4 rounds, 0 spare, no WeaponReload, auto drop 96); NOT an EAT-17 clone carrier: 5 extra '
        'components (Faction, GuidanceTarget, LaserDesignator, SensorEye, WeaponLinker) plus differing Backblast, '
        'DropMode and magazine; its own class has no other member, so no type-level clone has it as a carrier; pod '
        'capacity 1; a 1-round Commando is only the instance-local ammo override (HYPOTHESIS, not live)',
    'MGX-42 Bullet Storm': 'MEMBER (exists: entity expendable_machinegun, native stratagem Expendable_Machinegun, '
        'id 3288352984, its own exclusive rack; 300 rounds, 0 spare, chambered, no WeaponReload, auto drop 97); NOT an '
        'EAT-17 clone carrier: no Backblast component plus a differing EquipmentType, auto-drop ability and magazine; '
        'its own class has no other member; pod capacity 2 in the EAT-17 rack layout',
}


if __name__ == '__main__':
    main()
