"""Which (donor, carrier) pairs of support weapon TYPES can be carrier weapon clones, class by class? An extension of
scripts/research_carrier_weapon_clone.py (which only takes the EAT-17 as donor) to every ordered pair of distinct
members inside every component class with more than one member. Read-only, offline; nothing is written to the game.

For each pair, from the pinned entity tables, the go library, the retained snapshots and the game's archives:

1. The member diff (research_carrier_weapon_clone.member_diff, classified by its reviewed ASPECTS table).
2. Every differing member that the reviewed table leaves 'unreviewed', grouped by component.
3. A PROPOSED classification for those members: EXTRA_ASPECTS below (the reviewed ASPECTS table is never edited and
   always wins; EXTRA_ASPECTS only covers what it leaves unreviewed). Members EXTRA_ASPECTS cannot justify stay
   'unreviewed' / 'never'.
4. The carrier contract: every written record owned exclusively by the carrier type, the carrier in no world loot
   table, delivered only by its own stratagem, the same marker texture kind (Spottable +0x40) as the donor.
5. A verdict: 'eligible' or 'refused' with every reason, and the copy writes by level and by aspect.
6. Resource implications: the donor's loadout package, which donor resources it lists, and where every copied
   resource reference / node / animation-event hash is found.

The EAT-17 class is included as a regression check: EAT-17 -> EAT-700 / EAT-411 must reproduce the domain writes of
research/carrier-weapon-clone-F5FEE03DCFDB.json exactly.

Output: research/clone-classes-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import pickle
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import hd2_game_data  # noqa: E402
import research_carrier_weapon_clone as clone  # noqa: E402
import research_event_state as base  # noqa: E402
import research_support_item_presentation as presentation  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
from scan import golib, tables  # noqa: E402

OUTPUT = ROOT / 'research/clone-classes-F5FEE03DCFDB.json'
CACHE = ROOT / 'build/scan-cache/clone-classes-resources.pkl'
CLONE_RESEARCH = ROOT / 'research/carrier-weapon-clone-F5FEE03DCFDB.json'
PRESENTATION_RECORDS = ('EncyclopediaEntryComponentData', 'SpottableComponentData', 'LoadoutEntryComponentData')

# Proposed rows for members the reviewed ASPECTS table leaves unreviewed: (component, first offset, end offset,
# aspect, policy, label). Same rules as ASPECTS: model / animation / sound / effects / handling / firing values and
# unit-node / resource references -> copy; identity / loadout / package / customization-UI / hint ids -> never;
# members that decide the weapon's lifecycle contract -> identical (aspect 'expendable', the reviewed table's name
# for the lifecycle contract). Layouts: the go library (filediver datalibrary *.go) as aligned by scan.golib; the
# lead strength of every member is in the output. Anything not covered here stays unreviewed / never.
EXTRA_ASPECTS = [
    # WeaponReloadComponent (0x50; filediver weapon_reload_component.go, every lead STRONG except the last two VO).
    ('WeaponReloadComponentData', 0x0, 0x1, 'expendable', 'identical',
        'ManualClearing: "if true, the rules for fast/slow reload change" - a reload-model switch whose consumer is '
        'unproven; lifecycle (reload-ability) contract'),
    ('WeaponReloadComponentData', 0x1, 0x2, 'handling', 'copy',
        'ReloadAllowMove: whether the wielder may move while reloading - a handling flag'),
    ('WeaponReloadComponentData', 0x4, 0x8, 'animation', 'copy',
        'Ability: the ability played on the wielder for the reload (an AbilityId) - the reload counterpart of '
        'WeaponData +0x3AC FireAbility, which ASPECTS copies (animation)'),
    ('WeaponReloadComponentData', 0x8, 0x38, 'animation', 'copy',
        'ReloadAnimEvents[4] {Type (WeaponReloadEventType), weapon event, wielder event}: animation events per '
        'reload type (weapon side: the unit\'s state machine; wielder side: the avatar state machines)'),
    ('WeaponReloadComponentData', 0x38, 0x3C, 'handling', 'copy',
        'Duration: the reload duration (the reload ability is scaled to it)'),
    ('WeaponReloadComponentData', 0x3C, 0x40, 'expendable', 'identical',
        'HasSharedDeposit: ammo from a shared deposit on the entity it is mounted on - ammo-source linkage'),
    ('WeaponReloadComponentData', 0x40, 0x50, 'sound', 'copy',
        'ReloadVONormal / Lastmag / NoMags / NoMagsNoBackpack: VO events'),
    # WeaponRoundsComponent (0x88; weapon_rounds_component.go).
    ('WeaponRoundsComponentData', 0x0, 0x40, 'handling', 'copy',
        'AmmoInfo: recoil and spread modifiers per magazine'),
    ('WeaponRoundsComponentData', 0x40, 0x48, 'firing', 'copy',
        'AmmoType {primary, alternate projectile type}: the round fired per magazine - the counterpart of '
        'ProjectileWeapon +0 ProjType, which ASPECTS copies'),
    ('WeaponRoundsComponentData', 0x48, 0x6C, 'expendable', 'identical',
        'MagazineCapacity / AmmoCapacity / AmmoRefill / Ammo / ReloadAmount / ReloadThresholds / Chambered: the '
        'rounds ammunition model; kept identical like its reviewed counterpart, the WeaponMagazine record '
        '(instance ammo counters are seeded from it; resupply and HUD consumers unproven)'),
    ('WeaponRoundsComponentData', 0x6C, 0x70, 'sound', 'copy', 'MagazineSwitchAudio'),
    ('WeaponRoundsComponentData', 0x70, 0x84, 'animation', 'copy',
        'Magazine0/1 weapon and wielder anims, MagazineAnimVariable'),
    # WeaponChargeComponent (0xD8; weapon_charge_component.go). ChargeStateSettings[3] of 0x18 bytes each.
    *[row for k in range(3) for row in (
        ('WeaponChargeComponentData', 0x18 * k, 0x18 * k + 4, 'firing', 'copy',
            'ChargeStateSettings[%d].ChargeTime' % k),
        ('WeaponChargeComponentData', 0x18 * k + 4, 0x18 * k + 8, 'firing', 'copy',
            'ChargeStateSettings[%d].ProjType: the round fired at that charge state (ProjType counterpart)' % k),
        ('WeaponChargeComponentData', 0x18 * k + 8, 0x18 * k + 0x10, 'effects', 'copy',
            'ChargeStateSettings[%d].ProjectileParticle (particles resource)' % k))],
    ('WeaponChargeComponentData', 0x48, 0x78, 'firing', 'copy',
        'ProjMultipliers: speed / damage / penetration / arc multipliers by charge amount'),
    ('WeaponChargeComponentData', 0x78, 0x88, 'sound', 'copy',
        'ChargeStart / ChargeStop / ReadyToFire / DangerOvercharge sound ids'),
    ('WeaponChargeComponentData', 0x88, 0x94, 'model', 'copy',
        'ChargeMesh / ChargeMaterial / ChargeVariable: mesh, material and material-variable names on the unit'),
    ('WeaponChargeComponentData', 0x98, 0xA8, 'effects', 'copy',
        'ChargeUpMuzzleFlash / ChargeUpMuzzleFlashLoop (particles resources)'),
    ('WeaponChargeComponentData', 0xA8, 0xB8, 'animation', 'copy',
        'ChargeAnimID / ChargeEndAnimID / ChargeRateAnimID / SpinSpeedAnimID: weapon-unit animation variables'),
    ('WeaponChargeComponentData', 0xB8, 0xB9, 'firing', 'copy',
        'AutoFireInSafety: keep the charge while the trigger is held'),
    ('WeaponChargeComponentData', 0xC4, 0xC8, 'sound', 'copy', 'DryFireAudioEvent'),
    # NOT proposed (stay unreviewed): WeaponCharge +0x10/+0x28/+0x40 (17-character unknown thin hash), +0xB9 (bool,
    # filediver "ExplodesOnOvercharged", PLAUSIBLE: an unknown 24-character name), +0xBC / +0xC0 (unknown audio event
    # and float), +0xC8 ExplodeType (PLAUSIBLE) and +0xCC / +0xD0 StateValue {ChargeState, float}: together they decide
    # whether and when the weapon explodes on its wielder, and their names are unproven.
    # InteractableComponent: only zone 0's approach cone is reviewed here.
    ('InteractableComponentData', 0x48, 0x50, 'model', 'copy',
        'Zones[0].ApproachDirection / ApproachAngle: the pickup cone "in the interactable\'s local space" - a '
        'property of the item\'s model orientation, consistent only with the donor\'s unit'),
    # WeaponAssistedReloadComponent (0x68): no go-library layout, every member unnamed. Its role is reviewed
    # (EXTRA_COMPONENT_EFFECT: team reload from a backpack; filediver deposit_component.go AssistedReloadWeaponPath ties
    # a backpack to one weapon path): backpack linkage, lifecycle contract.
    ('WeaponAssistedReloadComponentData', 0x0, 0x68, 'expendable', 'identical',
        'team (assisted) reload from a backpack: backpack linkage; members unnamed (no go-library layout)'),
    # GuidanceTargetComponent (0x7C): no go-library layout, every member unnamed, no reviewed role: stays unreviewed.
]
NOT_PROPOSED = {
    'WeaponChargeComponentData': '+0x10/+0x28/+0x40 unknown thin hash, +0xB9 / +0xBC / +0xC0 / +0xC8 / +0xCC / +0xD0 '
        'the overcharge self-explosion block (PLAUSIBLE names only)',
    'GuidanceTargetComponentData': 'no go-library layout, every member unnamed, role unreviewed (lock-on / guidance)',
    'InteractableComponentData': 'every member except zone 0 +0x48..+0x50 (labels, hint ids, interact type, zones)',
}


def proposed_aspect(component: str, offset: int):
    """The reviewed table first (never overridden), then EXTRA_ASPECTS, then the default (unreviewed / never)."""
    reviewed = clone.aspect_of(component, offset)
    if reviewed != clone.DEFAULT_ASPECT:
        return reviewed + ('ASPECTS',)
    for comp, lo, hi, aspect, policy, label in EXTRA_ASPECTS:
        if comp == component and lo <= offset < hi:
            return aspect, policy, label, 'EXTRA_ASPECTS'
    return clone.DEFAULT_ASPECT + ('default',)


def check_extra_aspects(t: tables.EntityTables):
    """EXTRA_ASPECTS rows must lie inside their record, never overlap each other, and never shadow a reviewed row."""
    seen = {}
    for comp, lo, hi, *_ in EXTRA_ASPECTS:
        if not 0 <= lo < hi <= t.component(comp).record_size:
            raise ValueError('EXTRA_ASPECTS row outside %s: 0x%X..0x%X' % (comp, lo, hi))
        for a, b in seen.get(comp, []):
            if lo < b and a < hi:
                raise ValueError('EXTRA_ASPECTS rows overlap in %s at 0x%X' % (comp, lo))
        seen.setdefault(comp, []).append((lo, hi))
        if any(c == comp and lo < h and l < hi for c, l, h, *_ in clone.ASPECTS):
            raise ValueError('EXTRA_ASPECTS row shadows a reviewed ASPECTS row: %s 0x%X' % (comp, lo))


# ------------------------------------------------------------------------------------------------- delivery facts
def delivery_facts() -> tuple[set, dict]:
    """World loot entries and stratagem racks per item, exactly as research_support_item_presentation computes them
    (for every weapon, the EAT-17 included)."""
    pods = json.loads(presentation.POD_PAYLOADS.read_text(encoding='utf-8'))
    loot = {e for table in pods['worldLoot']['tables'] for e in table['entries']}
    racks = {}
    for rack in pods['racks']:
        for slot in rack['slots']:
            if slot['item']:
                racks.setdefault(slot['item'], set()).update(c['name'] for c in rack['consumers'])
    return loot, racks


# ------------------------------------------------------------------------------------------------- writes
def copy_writes(t: tables.EntityTables, donor: int, carrier: int, members: list[dict]) -> tuple[list, list]:
    """research_carrier_weapon_clone.copy_writes for any donor (that one is pinned to the EAT-17): every member with
    the copy policy as transaction-sized writes. Also returns every write that would cover a byte of a differing
    member whose policy is not copy (a bitfield neighbour), or whose width / alignment the transaction cannot take."""
    out, seen, problems = [], set(), []
    rows_a, rows_b = t.entity(donor), t.entity(carrier)
    for m in members:
        if m['policy'] != 'copy':
            continue
        comp = t.component(m['component'])
        offset = int(m['offset'], 16)
        rec_a, rec_b = comp.raw(rows_a[m['component']]), comp.raw(rows_b[m['component']])
        width = m['size']
        parts = [(offset, width)] if width in clone.WIDTHS else [(offset + k, 4) for k in range(0, width, 4)]
        for at, w in parts:
            key = (m['component'], at)
            if key in seen or rec_a[at:at + w] == rec_b[at:at + w]:
                continue
            seen.add(key)
            if w not in clone.WIDTHS or at % min(w, 4) or (width not in clone.WIDTHS and width % 4):
                problems.append('unsupported write width/alignment: %s +0x%X (%d)' % (m['component'], at, w))
                continue
            for other in members:
                o = int(other['offset'], 16)
                if other['component'] == m['component'] and other['policy'] != 'copy' and o < at + w and \
                        at < o + other['size']:
                    problems.append('write %s +0x%X (%d) covers %s member +0x%X (%s)' % (m['component'], at, w,
                        other['policy'], o, other['role']))
            out.append({'component': m['component'], 'offset': at, 'width': w, 'native': rec_b[at:at + w].hex(),
                'donor': rec_a[at:at + w].hex(), 'aspect': m['aspect'], 'level': clone.LEVEL_OF[m['aspect']],
                'label': (m['lead'] or m['role']) + (' (+%d)' % (at - offset) if at != offset else ''),
                'storage': m['storage'], 'source': m['source']})
    out.sort(key=lambda w: (w['component'], w['offset']))
    return out, problems


# ------------------------------------------------------------------------------------------------- archives
def class_resources(t: tables.EntityTables, members: dict) -> dict:
    """Every class member's unit (+ bones / physics / state machine), loadout package, optics and holster units, and
    the avatar state machines: the same archive reads as research_carrier_weapon_clone.read_resources, for any
    weapon, with the archive each one was found in. Cached in build/scan-cache."""
    types = {n: hd2_game_data.murmur64(n.encode()) for n in clone.RESOURCE_TYPES}
    uc, lp = t.component('UnitComponentData'), t.component('LoadoutPackageComponentData')
    wc, eq = t.component('WeaponCustomizationComponentData'), t.component('EquipmentComponentData')
    wanted, refs = {}, {}
    for key, resource in members.items():
        unit = struct.unpack_from('<Q', uc.raw(uc.record_of(resource)), 0)[0]
        package, audio = struct.unpack_from('<QQ', lp.raw(lp.record_of(resource)), 8)
        optics = struct.unpack_from('<Q', wc.raw(wc.record_of(resource)), 0x78)[0]
        holster = struct.unpack_from('<Q', eq.raw(eq.record_of(resource)), 0xC8)[0]
        refs[key] = {'unit': unit, 'package': package, 'audio': audio, 'optics': optics, 'holster': holster}
        wanted[(unit, types['unit'])] = key + '.unit'
        wanted[(package, types['package'])] = key + '.package'
        for kind in ('bones', 'physics', 'state_machine'):
            wanted[(unit, types[kind])] = key + '.' + kind
        for name, value in (('optics', optics), ('holster', holster)):
            if value and value != unit:
                wanted[(value, types['unit'])] = key + '.' + name
    for key, path in clone.AVATAR_STATE_MACHINES.items():
        wanted[(hd2_game_data.murmur64(path.encode()), types['state_machine'])] = 'avatar.' + key
    signature = clone.sha(repr(('v2 blobs archives bundles', sorted(wanted.items()))).encode())
    keys = ('blobs', 'archives', 'bundles')
    if CACHE.is_file():
        cached = pickle.loads(CACHE.read_bytes())
        if cached.get('signature') == signature:
            return {'types': types, 'refs': refs, **{k: cached[k] for k in keys}}
    data = hd2_game_data.Data()
    found = data.find(set(wanted))
    blobs = {wanted[key]: data.read(archive, main) for key, (archive, main, _stream, _gpu) in found.items()}
    archives = {wanted[key]: archive for key, (archive, *_rest) in found.items()}
    bundles = {key: bundle_entries(data, '%016x' % r['package']) for key, r in refs.items()}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps({'signature': signature, 'blobs': blobs, 'archives': archives,
        'bundles': bundles}))
    return {'types': types, 'refs': refs, 'blobs': blobs, 'archives': archives, 'bundles': bundles}


def bundle_entries(data: hd2_game_data.Data, name: str):
    """Every (name, type) the bundle (archive) of that name holds, read like hd2_game_data.Data.tables(); None when
    no bundle of that name exists."""
    if name not in data.items:
        return None
    head = data.item_bytes(name, 0, 72)
    if len(head) < 72 or struct.unpack_from('<I', head)[0] != 0xF0000011:
        return None
    types, files = struct.unpack_from('<II', head, 4)
    table = data.item_bytes(name, 0, 72 + 32 * types + 80 * files)
    start = 72 + 32 * types
    return {struct.unpack_from('<QQ', table, start + 80 * i) for i in range(files)}


def package_entries(blob: bytes) -> set:
    """Every (type, name) a package resource lists (the layout research_carrier_weapon_clone.package_contents reads)."""
    count = struct.unpack_from('<I', blob, 8)[0]
    return {struct.unpack_from('<QQ', blob, 16 + 16 * i) for i in range(count)}


def package_bundle(t: tables.EntityTables, res: dict, donor_key: str, writes: list[dict]) -> dict:
    """Does the bundle named after the donor's loadout package (the archive the asset loader opens for it) hold the
    donor's unit side, sight / holster units, sound bank and every copied resource reference?"""
    types, refs = res['types'], res['refs'][donor_key]
    entries = res['bundles'][donor_key]
    name = '%016x' % refs['package']
    if entries is None:
        return {'bundle': name, 'exists': False}
    names = {n for n, _kind in entries}
    holds = {k: (refs['unit'], types[k]) in entries for k in ('unit', 'bones', 'physics', 'state_machine')}
    for k in ('optics', 'holster'):
        if refs[k]:
            holds[k + 'Unit'] = (refs[k], types['unit']) in entries
    holds['audioResource'] = refs['audio'] in names
    copied = {}
    for w in writes:
        if w['width'] == 8 and w['storage'] == 'UINT64':
            value = struct.unpack('<Q', bytes.fromhex(w['donor']))[0]
            if value:
                copied['%s +0x%X' % (w['component'], w['offset'])] = value in names
    # The donor's default customization option (copied with WeaponCustomization +0x0..+0x8) brings its entity-delta
    # patches; a patch naming a resource needs that resource resident too.
    delta = {}
    for patch in res['customization'][donor_key]['deltaPatches']:
        offset = int(patch['offset'], 16)
        storage = next((m.storage for m in t.component(patch['component']).members() if m.offset == offset), None)
        if patch['size'] == 8 and storage == 'UINT64':
            value = int.from_bytes(bytes.fromhex(patch['bytes']), 'little')
            if value:
                delta['%s +%s' % (patch['component'], patch['offset'])] = {'resource': patch['resource'],
                    'inBundle': value in names}
    return {'bundle': name, 'exists': True, 'resources': len(entries), 'holds': holds,
        'copiedReferencesInBundle': copied, 'animations': sum(1 for _n, k in entries if k == types['animation']),
        'everyUnitSideResourceInBundle': all(holds.values()),
        'defaultCustomizationDeltaResources': delta}


def resource_implications(t: tables.EntityTables, res: dict, donor_key: str, writes: list[dict]) -> dict:
    types, blobs, archives = res['types'], res['blobs'], res['archives']
    refs = res['refs'][donor_key]
    type_name = {v: k for k, v in types.items()}
    blob = blobs.get(donor_key + '.package')
    if blob is None:
        return {'donorPackage': clone.hexid(refs['package']), 'status': 'donor package not found in the archives'}
    entries = package_entries(blob)
    names = {name for _kind, name in entries}

    def listed(value, kind):
        return (types[kind], value) in entries
    unit_side = b''.join(blobs.get(donor_key + '.' + k, b'') for k in ('unit', 'bones', 'physics'))
    own_sm = blobs.get(donor_key + '.state_machine', b'')
    tp, fp = blobs.get('avatar.thirdPerson', b''), blobs.get('avatar.firstPerson', b'')
    references, hashes = [], []
    for w in writes:
        raw = bytes.fromhex(w['donor'])
        if w['component'] == 'WeaponCustomizationComponentData' and w['offset'] < 8:
            continue  # DefaultCustomizations: a customization option id, see donorCustomization
        if w['width'] == 8 and w['storage'] == 'UINT64':
            value = struct.unpack('<Q', raw)[0]
            if value:
                kinds = sorted(type_name.get(k, '0x%016X' % k) for k, n in entries if n == value)
                references.append({'write': '%s +0x%X' % (w['component'], w['offset']), 'label': w['label'],
                    'value': clone.hexid(value), 'resource': t.paths.get(value),
                    'inDonorPackage': value in names, 'asTypes': kinds})
        elif w['width'] == 4 and w['storage'] == 'UINT32' and w['aspect'] in ('model', 'animation'):
            value = struct.unpack('<I', raw)[0]
            if value > 0xFFFF:
                needle = struct.pack('<I', value)
                where = [k for k, b in (('donorUnitBonesPhysics', unit_side), ('donorStateMachine', own_sm),
                    ('avatarThirdPerson', tp), ('avatarFirstPerson', fp)) if needle in b]
                hashes.append({'write': '%s +0x%X' % (w['component'], w['offset']), 'label': w['label'],
                    'value': '0x%08X' % value, 'thin': t.thin.get(value), 'foundIn': where})
    package_archive = archives.get(donor_key + '.package')
    found_in = {k.split('.', 1)[1]: archives[k] for k in archives if k.startswith(donor_key + '.')}
    return {
        'donorPackage': {'id': clone.hexid(refs['package']), 'name': t.paths.get(refs['package']),
            'archive': package_archive, 'entries': len(entries),
            'contents': clone.package_contents(t, blob, types)},
        'donorAudioResource': {'id': clone.hexid(refs['audio']), 'name': t.paths.get(refs['audio']),
            'listedInDonorPackageAs': sorted(type_name.get(k, '0x%016X' % k) for k, n in entries
                if n == refs['audio'])},
        'donorUnit': {'id': clone.hexid(refs['unit']), 'name': t.paths.get(refs['unit']),
            'listedAs': {k: listed(refs['unit'], k) for k in ('unit', 'bones', 'physics', 'state_machine')}},
        'donorOpticsUnit': None if not refs['optics'] else {'id': clone.hexid(refs['optics']),
            'name': t.paths.get(refs['optics']), 'listed': listed(refs['optics'], 'unit')},
        'donorHolsterUnit': None if not refs['holster'] else {'id': clone.hexid(refs['holster']),
            'name': t.paths.get(refs['holster']), 'listed': listed(refs['holster'], 'unit')},
        'donorCustomization': res['customization'][donor_key],
        'firstArchiveListingEachDonorResource': found_in,
        'donorPackageBundle': package_bundle(t, res, donor_key, writes),
        'copiedResourceReferences': references,
        'copiedReferencesNotInDonorPackage': [r['write'] for r in references if not r['inDonorPackage']],
        'copiedNodeAndAnimationHashes': hashes,
        'copiedHashesNotLocated': [h['write'] for h in hashes if not h['foundIn']],
        'notChecked': 'sound ids (wwise events live in the soundbanks the package lists; banks are not parsed here), '
            'effect resources\' own dependencies, ability ids (global ability table); archives are the FIRST bundle '
            'listing each resource (a resource may also ship in other bundles)',
    }


# ------------------------------------------------------------------------------------------------- snapshots
def type_tables_in_place(t: tables.EntityTables, components: list[str]) -> dict:
    """research_carrier_weapon_clone.snapshot_facts' in-place check, for the components a pair would write: the live
    type table equals the pinned file record block in every retained snapshot."""
    out = {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            em = mem.ptr(mem.game + clone.ENTITY_MANAGER)
            out[name] = {c: mem.read(mem.ptr(em + clone.slot_of(t, c)), len(t.component(c).body)) ==
                t.component(c).body for c in components}
        finally:
            mem.close()
    return out


# ------------------------------------------------------------------------------------------------- pairs
def evaluate(t, go, donor, carrier, names, loot, racks, backpack, res, keys, in_place) -> dict:
    dname, cname = names[donor], names[carrier]
    rows_a, rows_b = t.entity(donor), t.entity(carrier)
    diff = clone.member_diff(t, go, donor, carrier)
    members, unreviewed = [], {}
    for m in diff['members']:
        aspect, policy, label, source = proposed_aspect(m['component'], int(m['offset'], 16))
        row = dict(m, tableAspect=m['aspect'], tablePolicy=m['policy'], aspect=aspect, policy=policy, role=label,
            source=source)
        members.append(row)
        if m['aspect'] == 'unreviewed':
            unreviewed.setdefault(m['component'], []).append({'offset': m['offset'], 'size': m['size'],
                'storage': m['storage'], 'path': m['path'], 'lead': m['lead'], 'leadStrength': m['leadStrength'],
                'donor': m['donor'], 'carrier': m['carrier'], 'proposedAspect': aspect, 'proposedPolicy': policy,
                'proposedBy': source, 'proposal': label})
    writes, write_problems = copy_writes(t, donor, carrier, members)
    written = sorted({w['component'] for w in writes} | set(PRESENTATION_RECORDS))
    owners = {}
    for c in written:
        comp = t.component(c)
        owners[c] = {'carrierRecord': rows_b[c], 'carrierRecordOwners': [names.get(o, t.label(o))
            for o in comp.owners(rows_b[c])], 'donorRecord': rows_a[c]}
    exclusive = all(v['carrierRecordOwners'] == [cname] for v in owners.values())
    spot = t.component('SpottableComponentData')
    kind_a = struct.unpack_from('<I', spot.raw(rows_a['SpottableComponentData']), 0x40)[0]
    kind_b = struct.unpack_from('<I', spot.raw(rows_b['SpottableComponentData']), 0x40)[0]
    delivered = sorted(racks.get(clone.hexid(carrier), []))
    in_loot = clone.hexid(carrier) in loot
    identical_diffs = [m for m in members if m['policy'] == 'identical']
    still_unreviewed = [m for m in members if m['aspect'] == 'unreviewed']
    table_unreviewed = [m for m in members if m['tableAspect'] == 'unreviewed']
    reasons = []
    if set(rows_a) != set(rows_b):
        reasons.append('component sets differ')
    for c, v in owners.items():
        if v['carrierRecordOwners'] != [cname]:
            reasons.append('%s record %d is not owned by the carrier alone: %s' % (c, v['carrierRecord'],
                v['carrierRecordOwners']))
    if in_loot:
        reasons.append('the carrier is in a world loot table')
    if delivered != [cname]:
        reasons.append('the carrier is not delivered only by its own stratagem: deliveredBy %s' % delivered)
    if kind_a != kind_b:
        reasons.append('marker texture kind (Spottable +0x40) differs: donor %d, carrier %d' % (kind_a, kind_b))
    for m in identical_diffs:
        reasons.append('identical-policy member differs: %s %s %s (%s; donor %s, carrier %s)' % (m['component'],
            m['offset'], m['lead'] or '', m['role'], json.dumps(m['donor']), json.dumps(m['carrier'])))
    for m in still_unreviewed:
        reasons.append('unreviewed member differs: %s %s %s' % (m['component'], m['offset'], m['lead'] or ''))
    reasons += write_problems
    if backpack.get(dname) or backpack.get(cname):
        reasons.append('backpack-dependent (donor %s, carrier %s): the backpack is a separate entity type (its own '
            'Deposit; AssistedReloadWeaponPath ties it to one weapon path) that no weapon clone converts'
            % (backpack.get(dname), backpack.get(cname)))
    verdict = 'refused' if reasons else 'eligible'
    gaps = sorted(c for c in {w['component'] for w in writes} if c not in clone.DOMAIN_COMPONENTS)
    by_level = {lvl: sum(1 for w in writes if w['level'] == lvl) for lvl in ('model', 'full')}
    by_aspect = {}
    for w in writes:
        by_aspect[w['aspect']] = by_aspect.get(w['aspect'], 0) + 1
    copy_members = {}
    for m in members:
        if m['policy'] == 'copy':
            copy_members[m['aspect']] = copy_members.get(m['aspect'], 0) + 1
    return {
        'donor': dname, 'carrier': cname, 'donorEntity': clone.hexid(donor), 'carrierEntity': clone.hexid(carrier),
        'verdict': verdict, 'refusalReasons': reasons,
        'verdictWithReviewedTableOnly': 'refused' if reasons or table_unreviewed else 'eligible',
        'differingMembers': len(members),
        'differingByAspect': {k: sum(1 for m in members if m['aspect'] == k) for k in sorted({m['aspect']
            for m in members})},
        'copyMembersByAspect': dict(sorted(copy_members.items())),
        'copyWrites': len(writes), 'copyWritesByLevel': by_level, 'copyWritesByAspect': dict(sorted(by_aspect.items())),
        'unreviewedByReviewedTable': unreviewed,
        'contract': {'componentSetsIdentical': set(rows_a) == set(rows_b), 'writtenRecords': owners,
            'everyWrittenRecordExclusive': exclusive, 'inWorldLoot': in_loot, 'deliveredBy': delivered,
            'markerKind': {'donor': kind_a, 'carrier': kind_b, 'equal': kind_a == kind_b},
            'backpackDependent': {'donor': backpack.get(dname), 'carrier': backpack.get(cname)}},
        'implementationGaps': {'componentsOutsideTheCloneDomain': gaps,
            'meaning': 'copy writes into components runtime/weapon_clone.lua has no schema for (DOMAIN_COMPONENTS of '
                'research_carrier_weapon_clone); each needs its consumer / read-in-place proof before any write',
            'typeTableInPlaceInEverySnapshot': {c: all(in_place[s][c] for s in in_place) for c in gaps}},
        'resources': resource_implications(t, res, keys[donor], writes),
        'writes': writes,
        'members': [{k: m[k] for k in ('component', 'offset', 'size', 'storage', 'path', 'lead', 'leadStrength',
            'aspect', 'policy', 'role', 'source', 'tableAspect', 'tablePolicy', 'donor', 'carrier')} for m in members],
    }


def regression(t, go, pairs: list[dict], names: dict) -> dict:
    """EAT-17 -> EAT-700 / EAT-411 against research/carrier-weapon-clone-F5FEE03DCFDB.json, and the original
    copy_writes (pinned to the EAT-17) against this script's generic one."""
    stored = json.loads(CLONE_RESEARCH.read_text(encoding='utf-8'))
    hosts = stored['checks']['eat17CloneHosts']
    out = {}
    for p in pairs:
        if p['donor'] != 'EAT-17 Expendable Anti-Tank':
            continue
        carrier = int(p['carrierEntity'], 16)
        diff = clone.member_diff(t, go, clone.DONOR, carrier)
        diff['carrierRecords'] = t.entity(carrier)
        original = clone.copy_writes(t, diff)
        mine = [{k: w[k] for k in ('component', 'offset', 'width', 'native', 'donor', 'aspect', 'level', 'label')}
            for w in p['writes']]
        domain = stored['domain']['carriers'].get(p['carrier'])
        candidate = next((c for c in stored['carrierCandidates'] if c['weapon'] == p['carrier']), {})
        out[p['carrier']] = {
            'writesEqualOriginalCopyWrites': mine == original,
            'writesEqualStoredDomain': domain is not None and mine == domain['writes'],
            'levelsEqualStoredDomain': domain is not None and p['copyWritesByLevel'] == domain['levels'],
            'verdictEqualsStoredHost': (p['verdict'] == 'eligible') == (p['carrier'] in hosts),
            'differingMembersEqualStored': len(p['members']) == candidate.get('differingMembers'),
            'contractEqualsStored': p['contract']['inWorldLoot'] == candidate.get('inWorldLoot') and
                p['contract']['deliveredBy'] == candidate.get('deliveredBy') and
                p['contract']['everyWrittenRecordExclusive'] == candidate.get('everyWrittenRecordExclusive'),
        }
    if set(out) != {'EAT-700 Expendable Napalm', 'EAT-411 Leveller'} or not all(all(v.values())
            for v in out.values()):
        raise ValueError('EAT-17 regression failed: %r' % out)
    return out


def delivery_cross_check(stored: dict, loot: set, racks: dict) -> dict:
    """This script's loot / rack facts against the stored carrierCandidates (every weapon but the EAT-17)."""
    mismatches = [c['weapon'] for c in stored['carrierCandidates'] if (c['resource'] in loot) != c['inWorldLoot']
        or sorted(racks.get(c['resource'], [])) != c['deliveredBy']]
    if mismatches:
        raise ValueError('delivery facts differ from the stored research: %r' % mismatches)
    return {'checkedAgainstStoredCarrierCandidates': len(stored['carrierCandidates']), 'mismatches': mismatches}


# ------------------------------------------------------------------------------------------------- main
def main():
    t = tables.pinned()
    go = golib.default_library()
    check_extra_aspects(t)
    by_path = clone.names_by_path()
    weapons = t.find('equipment/support_weapons/')
    names = {}
    for name, rows in json.loads(clone.EQUIPMENT_LINKS.read_text(encoding='utf-8'))['supportWeapons'].items():
        for row in rows:
            names.setdefault(int(row['resource'], 16), name)
    names.update({r: by_path.get(t.label(r), t.label(r)) for r in weapons})
    all_sets = {}
    for r in t.resources():
        all_sets.setdefault(frozenset(t.entity(r)), []).append(r)
    # A class is every entity TYPE with a support weapon's exact component set, wherever its path lies (the M-105
    # Stalwart lives under primary_weapons/, the TX-41 Sterilizer has no path name): components are fixed per type, so
    # any such type is a clone candidate exactly like the 27 under equipment/support_weapons/.
    sets = {}
    for r in weapons:
        sets.setdefault(frozenset(t.entity(r)), all_sets[frozenset(t.entity(r))])
    outside = sorted({r for rs in sets.values() for r in rs if r not in weapons}, key=t.label)
    for r in outside:
        names.setdefault(r, t.label(r))
    loot, racks = delivery_facts()
    stored = json.loads(CLONE_RESEARCH.read_text(encoding='utf-8'))
    delivery_check = delivery_cross_check(stored, loot, racks)
    backpack = {row.get('catalogIdentity'): row.get('backpackDependent') for row in
        json.loads(clone.SUPPORT_RUNTIME.read_text(encoding='utf-8'))['weapons']}
    classes = sorted((sorted(rs, key=lambda r: names[r]) for rs in sets.values() if len(rs) > 1),
        key=lambda rs: names[rs[0]])
    keys = {r: t.label(r) for rs in classes for r in rs}
    res = class_resources(t, {keys[r]: r for r in keys})
    res['customization'] = clone.customization_options(t, {keys[r]: r for r in keys})
    written = set()
    for rs in classes:
        for a in rs:
            for b in rs:
                if a != b:
                    d = clone.member_diff(t, go, a, b)
                    written |= {m['component'] for m in d['members']}
    in_place = type_tables_in_place(t, sorted(written - set(clone.DOMAIN_COMPONENTS)))
    pairs = [evaluate(t, go, a, b, names, loot, racks, backpack, res, keys, in_place)
        for rs in classes for a in rs for b in rs if a != b]
    reg = regression(t, go, pairs, names)
    singletons = []
    for s, rs in sorted(sets.items(), key=lambda kv: names[kv[1][0]]):
        if len(rs) != 1:
            continue
        r = rs[0]
        others = [o for o in weapons if o != r]
        nearest = min(others, key=lambda o: (len(s ^ set(t.entity(o))), names[o]))
        singletons.append({'weapon': names[r], 'entity': t.label(r), 'components': len(s),
            'entityTypesWithThisComponentSet': [t.label(o) for o in all_sets[s]],
            'nearestSupportWeapon': names[nearest],
            'missingVsNearest': sorted(set(t.entity(nearest)) - s),
            'extraVsNearest': sorted(s - set(t.entity(nearest))),
            'why': 'no other entity type has this exact component set, and components are fixed per type: no clone '
                'pair exists (as donor or as carrier)'})
    class_rows = []
    for rs in classes:
        s = frozenset(t.entity(rs[0]))
        class_rows.append({'members': [names[r] for r in rs], 'components': sorted(s),
            'membersOutsideSupportWeaponsPath': [{'name': names[r], 'entity': clone.hexid(r), 'label': t.label(r),
                'path': t.name(r)} for r in rs if r not in weapons],
            'sharedRecords': {c: [names[r] for r in rs] for c in sorted(s)
                if len({t.entity(r)[c] for r in rs}) < len(rs)}})
    unreviewed_rows = {}
    for p in pairs:
        for comp, rows in p['unreviewedByReviewedTable'].items():
            for row in rows:
                key = '%s %s' % (comp, row['offset'])
                u = unreviewed_rows.setdefault(key, {'component': comp, 'offset': row['offset'], 'size': row['size'],
                    'storage': row['storage'], 'path': row['path'], 'lead': row['lead'],
                    'leadStrength': row['leadStrength'], 'proposedAspect': row['proposedAspect'],
                    'proposedPolicy': row['proposedPolicy'], 'proposedBy': row['proposedBy'],
                    'proposal': row['proposal'], 'pairs': []})
                u['pairs'].append('%s -> %s' % (p['donor'], p['carrier']))
    summary = [{'donor': p['donor'], 'carrier': p['carrier'], 'verdict': p['verdict'],
        'verdictWithReviewedTableOnly': p['verdictWithReviewedTableOnly'], 'copyWritesByLevel': p['copyWritesByLevel'],
        'copyWritesByAspect': p['copyWritesByAspect'], 'refusalReasons': len(p['refusalReasons'])} for p in pairs]
    result = {
        'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'sources': {'reviewedAspects': 'scripts/research_carrier_weapon_clone.py ASPECTS (%d rows, unchanged)'
            % len(clone.ASPECTS), 'proposedAspects': 'EXTRA_ASPECTS (%d rows) in this script' % len(EXTRA_ASPECTS),
            'notProposed': NOT_PROPOSED},
        'extraAspects': [{'component': c, 'from': '0x%X' % lo, 'to': '0x%X' % hi, 'aspect': a, 'policy': p,
            'label': label} for c, lo, hi, a, p, label in EXTRA_ASPECTS],
        'universe': {'supportWeaponsPath': len(weapons), 'sameSetTypesOutsideThePath': [{'name': names[r],
            'entity': clone.hexid(r), 'label': t.label(r), 'path': t.name(r)} for r in outside],
            'rule': 'the 27 entity types under equipment/support_weapons/ plus every other entity type (any path) '
                'with one of their exact component sets'},
        'classes': class_rows,
        'singletons': singletons,
        'deliveryFacts': delivery_check,
        'unreviewedMembers': sorted(unreviewed_rows.values(), key=lambda u: (u['component'], int(u['offset'], 16))),
        'summary': summary,
        'eligiblePairs': ['%s -> %s' % (p['donor'], p['carrier']) for p in pairs if p['verdict'] == 'eligible'],
        'eligiblePairOpenItems': {'%s -> %s' % (p['donor'], p['carrier']): {
            'defaultCustomization': p['resources']['donorCustomization']['optionDebugName'] or
                p['resources']['donorCustomization']['defaultOption'],
            'defaultCustomizationDeltaPatches': len(p['resources']['donorCustomization']['deltaPatches']),
            'defaultCustomizationDeltaResources': p['resources']['donorPackageBundle'].get(
                'defaultCustomizationDeltaResources'),
            'copiedReferencesNotInDonorBundle': [k for k, v in p['resources']['donorPackageBundle'].get(
                'copiedReferencesInBundle', {}).items() if not v],
            'copiedHashesNotLocated': p['resources']['copiedHashesNotLocated'],
            'neverMembersThatDiffer': ['%s %s (%s)' % (m['component'], m['offset'], m['role']) for m in p['members']
                if m['policy'] == 'never']} for p in pairs if p['verdict'] == 'eligible'},
        'donorBundles': {p['donor']: {'bundle': p['resources']['donorPackageBundle'].get('bundle'),
            'everyUnitSideResourceInBundle': p['resources']['donorPackageBundle'].get('everyUnitSideResourceInBundle'),
            'copiedReferencesNotInBundle': sorted({k for q in pairs if q['donor'] == p['donor'] for k, v in
                q['resources']['donorPackageBundle'].get('copiedReferencesInBundle', {}).items() if not v})}
            for p in pairs},
        'regressionEat17': reg,
        'typeTablesInPlace': in_place,
        'pairs': pairs,
    }
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pairs', len(pairs), '; eligible', result['eligiblePairs'],
        '; regression', {k: all(v.values()) for k, v in reg.items()})


if __name__ == '__main__':
    main()
