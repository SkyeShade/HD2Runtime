"""Every beam a weapon fires, who fires it, and which member a beam swap must write. Read-only research.

Question (0.30.4, "lasers everywhere"): can every beam host fire any other weapon's beam, the way projectile hosts take
projectile donors (docs/attack-outputs.md)? A beam is fired only by a BeamWeaponComponent; its +0 (typed BeamType) names
the BeamSettings row (BeamInfo: length, radius, damage row, hit effects, the beam's visual resources) the weapon fires.
Nothing outside the beam system references a BeamType (research/attack-outputs typeReferences), so a beam reference can
only ever be a BeamWeapon +0 write on a weapon that already owns that component.

This inventories, from the pinned decoded entity table, the retained snapshot (settings rows by the production
resolver) and the installed game data (package listings):

1. Every BeamWeaponComponent record (the table has 24), its owner entities, each owner's name and kind (player, support,
   sentry, drone, enemy, structure, other roots) from the Runtime's own catalogues and research, its fire mode / rate /
   pulse members and the BeamSettings row of its +0.
2. Every entity delta that patches the BeamWeapon component (component index 270), decoded like the ammunition deltas of
   research/active-projectile-sources: which customization item carries it and which weapons default to it. A default
   customization that patches +0 makes the base member dormant (the Liberator lesson): its delta is the active source.
3. Each owner's active beam source: ACTIVE_DIRECT (no default or equippable customization patches BeamWeapon +0: the
   record's +0 is what it fires), INDIRECT (exactly one default item patches +0 in its own 4-byte delta row: that row is
   the active source) or AMBIGUOUS / BLOCKED with the reason.
4. Each beam row's resources (BeamInfo +48 / +56 / +64, u64) and whether the owner's own loadout package lists them, so a
   donor's assets can be loaded before a swap (core/assets), and which packages are unknown.

No native reader of the beam firing path was traced, as for projectiles: the classification rests on the decoded data
path. Nothing here writes game memory.

Output: research/beam-outputs-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from migration import build_view  # noqa: E402
import research_attack_outputs as attack_outputs  # noqa: E402
from research_magazine_attachments import DATALIB, DELTAS_SHA, customization_items, entity_deltas, sha  # noqa: E402

OUTPUT = ROOT / 'research/beam-outputs-F5FEE03DCFDB.json'
BEAM = 'BeamWeaponComponentData'
BEAM_INDEX = 270
CUSTOMIZATION = 'WeaponCustomizationComponentData'
PARTICLES = 0xA8193123526FAD64  # murmur64('particles')
RESOURCE_MEMBERS = (48, 56, 64)  # BeamInfo u64 members (hidden-name lengths 16 / 19 / 14): the beam's resources
WEAPON_ROOTS = ROOT / 'research/weapon-roots-F5FEE03DCFDB.json'
DEFENSIVE = ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json'
ENEMY_ATTACKS = ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json'
ENEMY_AUTHORING = ROOT / 'research/enemy-authoring-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
UNLOCK_LISTS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
SUPPORT_RUNTIME = ROOT / 'domains/support_weapon_authoring.lua'
FIRE_MODES = {4: 'continuous', 5: 'charged', 6: 'pulsed'}


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def hexid(value):
    return f'0x{value:016X}'


def prove_layout(native):
    """BeamWeapon component index and its typed members, from the pinned library (fails closed on drift)."""
    found = native.probe.find_component(native.entities, BEAM)
    if u32(native.entities, found[4] - 4) != BEAM_INDEX:
        raise ValueError('BeamWeaponComponentData component index changed')
    members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, 'BeamWeaponComponent',
        structured=True)['members']}
    if members[0]['type_hash'] != native.probe.dl_hash('BeamType') or members[0]['size64'] != 4:
        raise ValueError('BeamWeaponComponent +0 is no longer a BeamType')
    if members[100]['size64'] != 4 or members[104]['size64'] != 4:
        raise ValueError('BeamWeaponComponent fire mode / rate layout changed')
    body, _, _, size, count = native.table(BEAM)
    if size != 120:
        raise ValueError('BeamWeaponComponent record size changed')
    info = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, 'BeamInfo', structured=True)['members']}
    if info[12]['type_hash'] != native.probe.dl_hash('DamageInfoType') or any(info[o]['size64'] != 8
            for o in RESOURCE_MEMBERS):
        raise ValueError('BeamInfo layout changed')
    return {'componentIndex': BEAM_INDEX, 'recordSize': size, 'records': count,
        'members': {'0': 'BeamType (typed enum): the beam row the weapon fires', '100': 'fire mode (typed enum 4/5/6)',
            '104': 'fire rate (beam.fire_rate)', '108': 'beam.pulse_beams (lead)', '112': 'beam.pulse_seconds (lead)'},
        'beamInfo': {'12': 'DamageInfoType (typed)', '4': 'radius', '8': 'length',
            '48/56/64': 'u64 resources (effects; checked against the owner package)', '96': 'ExplosionType (typed)'}}


def owner_names(native):
    """resource -> (name, kind, note) from the Runtime catalogues and research (no guessing: unnamed stays None)."""
    names = {}
    for name, kind, resource in attack_outputs.weapons():
        names[int(resource, 16)] = (name, kind, None)
    for item in json.loads(WEAPON_ROOTS.read_text(encoding='utf-8'))['corrections']:
        for dropped in item.get('droppedRoots', []):
            names.setdefault(int(dropped, 16), (item['weapon'] + ' (dropped root)', 'dropped_root', item['droppedIs']))
    text = SUPPORT_RUNTIME.read_text(encoding='utf-8')
    for name in ('LAS-98 Laser Cannon',):
        start = text.find('["' + name + '"]={')
        window = text[start:start + 400000]
        marker = window.find('["nonDeliveredRoots"]={')
        if marker >= 0:
            roots = window[marker:window.find('}', marker)]
            for value in roots.split('"')[1::2]:
                if value.startswith('0x'):
                    names.setdefault(int(value, 16), (name + ' (non-delivered root)', 'other_root',
                        'a root the LAS-98 support research matched but that the stratagem does not deliver'))
    for item in json.loads(DEFENSIVE.read_text(encoding='utf-8'))['stratagems']:
        entity = item.get('deployedEntity') or {}
        if entity.get('resource'):
            # The Laser Sentry's deployed entity is also one of the LAS-98's non-delivered roots: the stratagem wins.
            names[int(entity['resource'], 16)] = (item['name'], 'sentry', None)
    mounted_on = collections.defaultdict(list)
    for cls in json.loads(ENEMY_ATTACKS.read_text(encoding='utf-8'))['classes']:
        for slot in cls.get('slots', []):
            if slot.get('family') == 'beam':
                value = int(slot['weapon'], 16)
                if cls['name'] not in [c['name'] for c in mounted_on[value]]:
                    mounted_on[value].append(cls)
    for value, classes in mounted_on.items():
        names[value] = ('beam weapon of ' + ' / '.join(c['name'] for c in classes) + ' (' + classes[0]['faction']
            + ' ' + classes[0]['kind'] + ')', 'enemy', None)
    for cls in json.loads(ENEMY_AUTHORING.read_text(encoding='utf-8'))['classes']:
        names.setdefault(int(cls['resource'], 16), (cls['className'] + ' (' + cls['faction'] + ' ' + cls['kind'] + ')',
            'enemy' if cls['kind'] == 'enemy' else 'enemy_structure', None))
    return names


def residency_keys():
    """Owner resource -> [(asset catalog key, package id, package name)] (research/package-residency, exact resource)."""
    catalog = json.loads(RESIDENCY.read_text(encoding='utf-8'))['catalog']
    out = collections.defaultdict(list)
    for key, item in sorted(catalog.items()):
        dependency = item.get('dependency')
        if item.get('resource') and dependency:
            out[int(item['resource'], 16)].append((key, int(dependency['package'], 16), dependency['name']))
    return out


def package_listings(wanted_packages):
    """Package id -> set of resource name hashes it lists (installed game data, read-only)."""
    import hd2_game_data
    listed = collections.defaultdict(set)
    for archive, rname, rtype, *_ in hd2_game_data.Data().tables():
        package = int(archive, 16)
        if package in wanted_packages:
            listed[package].add(rname)
    return listed


def build():
    native = attack_outputs.entity_research.Native()
    layout = prove_layout(native)
    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    deltas, _ = entity_deltas(deltas_file)
    items = customization_items((DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    by_add = {item['addPath']: item for item in items}
    by_id = {item['optionId']: item for item in items}
    unlock = {int(e['resource'], 16): e for e in json.loads(UNLOCK_LISTS.read_text())['weapons'] if e.get('resource')}
    names = owner_names(native)
    keys = residency_keys()

    # 2. Every entity delta that patches the BeamWeapon component.
    patches = []
    for add_path, delta in sorted(deltas.items()):
        entries = [e for e in delta['entries'] if e['component'] == BEAM_INDEX]
        if not entries:
            continue
        item = by_add.get(add_path)
        base = [e for e in entries if e['offset'] == 0]
        patches.append({'addPath': hexid(add_path), 'item': item['debugName'] if item else None,
            'optionId': f"0x{item['optionId']:08X}" if item else None, 'slots': item['slots'] if item else None,
            'hashmapSlot': delta['hashmapSlot'], 'settingsIndex': delta['settingsIndex'],
            'members': [{'offset': e['offset'], 'size': e['size'], 'dataOffset': e['dataOffset'],
                'value': e['bytes'].hex()} for e in entries],
            'beamType': u32(base[0]['bytes'], 0) if base else None,
            'beamTypeOwnRow': bool(base) and base[0]['size'] == 4,
            'beamTypeDataOffset': base[0]['dataOffset'] if base else None})
    patch_by_add = {int(p['addPath'], 16): p for p in patches}

    # 1. Every BeamWeapon record and its owners.
    owners = native.owners(BEAM)
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    beam_table = view.settings['beam']
    records, beam_types = [], set()
    for index in range(layout['records']):
        raw = native.record(BEAM, index)
        beam_type = u32(raw, 0)
        beam_types.add(beam_type)
        entry = {'record': index, 'beamType': beam_type, 'fireMode': u32(raw, 100),
            'fireModeName': FIRE_MODES.get(u32(raw, 100)), 'fireRate': struct.unpack_from('<i', raw, 104)[0],
            'pulseBeams': struct.unpack_from('<i', raw, 108)[0],
            'pulseSeconds': round(struct.unpack_from('<f', raw, 112)[0], 4), 'owners': []}
        for resource in sorted(owners.get(index, [])):
            component = native.component(hexid(resource), BEAM)
            components = {c['name']: c for c in native.report(hexid(resource))['components']
                if c['resolved'] and c['name']}
            name, kind, note = names.get(resource, (None, 'unnamed', None))
            owner = {'resource': hexid(resource), 'path': native.path(resource), 'name': name, 'kind': kind,
                'note': note, 'entityRow': native.entity_row(resource),
                'componentIdentity': {'recordIndex': component['record_index'], 'indexRow': component['index_row'],
                    'ownerCount': len(owners[index]), 'uniqueOwner': len(owners[index]) == 1},
                'fireResource': sorted(c.removesuffix('ComponentData') for c in components
                    if c.startswith('Weapon') and c != CUSTOMIZATION),
                'otherOutputs': sorted(c.removesuffix('ComponentData') for c in components if c in (
                    'ProjectileWeaponComponentData', 'ArcWeaponComponentData', 'SprayWeaponComponentData'))}
            # 3. Default customization (slot, option) pairs and the equippable options that patch BeamWeapon.
            defaults = []
            if CUSTOMIZATION in components:
                body = native.record(CUSTOMIZATION, components[CUSTOMIZATION]['record_index'])
                for at in range(0, 80, 8):
                    slot, option = struct.unpack_from('<II', body, at)
                    item = by_id.get(option)
                    if item and item['addPath'] in patch_by_add:
                        defaults.append({'slot': slot, 'item': item['debugName'], 'optionId': f'0x{option:08X}',
                            'pairOffset': at, 'addPath': hexid(item['addPath']),
                            'beamType': patch_by_add[item['addPath']]['beamType']})
            equippable = [{'item': o['debugName'], 'addPath': o['addPath'],
                    'beamType': patch_by_add[int(o['addPath'], 16)]['beamType']}
                for o in (unlock.get(resource) or {}).get('options', [])
                if int(o['addPath'], 16) in patch_by_add
                and not any(int(d['addPath'], 16) == int(o['addPath'], 16) for d in defaults)]
            base_overrides = [d for d in defaults if d['beamType'] is not None]
            if not owner['componentIdentity']['uniqueOwner']:
                status, reason, source = 'BLOCKED', 'The BeamWeapon record is shared by several entities.', None
            elif len(base_overrides) > 1:
                status, reason, source = 'AMBIGUOUS', ('Several default customization items patch BeamWeapon +0; the '
                    'applied order is not proven.'), None
            elif base_overrides:
                item = base_overrides[0]
                patch = patch_by_add[int(item['addPath'], 16)]
                if not patch['beamTypeOwnRow']:
                    status, reason, source = 'AMBIGUOUS', ('The default item ' + item['item'] + ' patches BeamWeapon +0 '
                        'inside a wider delta row.'), None
                else:
                    status = 'INDIRECT'
                    reason = ('The default customization item ' + item['item'] + ' (slot ' + str(item['slot']) + ') '
                        'patches BeamWeapon +0 (to BeamType ' + str(item['beamType']) + ') when the weapon is built, '
                        'so the base member is dormant; that delta row is the active beam source.')
                    if equippable:
                        reason += (' Its unlock list also carries ' + ', '.join(e['item'] for e in equippable)
                            + ', which patch BeamWeapon +0 too.')
                        status = 'AMBIGUOUS'
                    source = {'kind': 'customization_delta', 'item': item['item'], 'slot': item['slot'],
                        'optionId': item['optionId'], 'defaultPairOffset': item['pairOffset'],
                        'addPath': item['addPath'], 'hashmapSlot': patch['hashmapSlot'],
                        'settingsIndex': patch['settingsIndex'], 'dataOffset': patch['beamTypeDataOffset'],
                        'value': item['beamType'], 'baseAgrees': item['beamType'] == beam_type,
                        'otherMembers': [m['offset'] for m in patch['members'] if m['offset'] != 0]}
            elif equippable:
                status, reason, source = 'AMBIGUOUS', ('No default overrides BeamWeapon +0, but the unlock list carries '
                    + ', '.join(e['item'] for e in equippable) + ', which patch it: the fired beam depends on the '
                    'equipped option.'), None
            else:
                status, reason, source = 'ACTIVE_DIRECT', ('No default or equippable customization patches BeamWeapon '
                    '+0 and nothing else references a BeamType: the record\'s +0 is the beam it fires.'), {
                    'kind': 'component', 'value': beam_type}
            if status == 'INDIRECT' and kind not in ('player_weapon', 'dropped_root'):
                # Applying default customization deltas when a weapon is built is live-proven for player weapons only
                # (the AR-23 Liberator ammunition test). A mounted drone weapon whose delta names another beam than
                # its record stays unproven: either member could be the one it fires.
                status = 'AMBIGUOUS'
                reason = ('Its default customization item ' + source['item'] + ' patches BeamWeapon +0 to BeamType '
                    + str(source['value']) + ', but its record names BeamType ' + str(beam_type) + '. That the game '
                    'applies customization deltas when it builds a weapon is live-proven for player weapons only (the '
                    'AR-23 Liberator ammunition), not for a ' + kind.replace('_', ' ') + ', and the wiki publishes '
                    'the record\'s row (its damage), not the delta\'s. Which beam it fires is not proven offline.')
                source = dict(source, kind='candidate_customization_delta')
            owner.update(defaultCustomization=defaults, equippableBeamOptions=equippable, status=status,
                reason=reason, activeSource=source, unlockList=resource in unlock)
            owner['packages'] = [{'key': key, 'package': hexid(package), 'name': package_name}
                for key, package, package_name in keys.get(resource, [])]
            entry['owners'].append(owner)
        records.append(entry)
    beam_types |= {p['beamType'] for p in patches if p['beamType'] is not None}

    # Settings rows of every beam type a record or a delta names (production resolver on the retained snapshot), with
    # the raw row members a swap brings along.
    rows = attack_outputs.resolve_settings([], sorted(beam_types), [])['beams']
    for value in sorted(beam_types):
        row = rows.get(str(value))
        found = beam_table.row_for_type(value)
        if not row or not found:
            rows[str(value)] = None
            continue
        raw = found[0][1]
        row['resources'] = {str(o): hexid(struct.unpack_from('<Q', raw, o)[0]) for o in RESOURCE_MEMBERS
            if struct.unpack_from('<Q', raw, o)[0]}
        row['hitEffectDamageType'] = u32(raw, 88)
        row['pulseRowFlag'] = raw[108]
    consumers = collections.defaultdict(list)
    for entry in records:
        for owner in entry['owners']:
            consumers[entry['beamType']].append(owner['name'] or owner['path'] or owner['resource'])
    delta_consumers = collections.defaultdict(list)
    for patch in patches:
        if patch['beamType'] is not None:
            delta_consumers[patch['beamType']].append(patch['item'] or patch['addPath'])

    # 4. Do the owner packages list the beam's resources?
    wanted = {int(p['package'], 16) for e in records for o in e['owners'] for p in o['packages']}
    listings = package_listings(wanted)
    for entry in records:
        row = rows.get(str(entry['beamType']))
        for owner in entry['owners']:
            for package in owner['packages']:
                listed = listings.get(int(package['package'], 16), set())
                package['listsBeamResources'] = bool(row and row['resources']) and all(
                    int(value, 16) in listed for value in row['resources'].values())
                package['listsOwner'] = int(owner['resource'], 16) in listed
    summary = {'records': len(records), 'owners': sum(len(e['owners']) for e in records),
        'beamTypes': len({e['beamType'] for e in records}),
        'byKind': dict(sorted(collections.Counter(o['kind'] for e in records for o in e['owners']).items())),
        'byStatus': dict(sorted(collections.Counter(o['status'] for e in records for o in e['owners']).items())),
        'beamDeltas': len(patches), 'beamDeltasPatchingBeamType': sum(1 for p in patches if p['beamType'] is not None)}
    return {'schemaVersion': 1, 'build': 'F5FEE03DCFDB', 'writes': 0, 'snapshot': build_profile.SNAPSHOT.name,
        'entityDeltasSha256': DELTAS_SHA, 'layout': layout,
        'proofBasis': ('Decoded data path: the pinned entity table (records, owners, default customization pairs), the '
            'pinned entity delta table (every delta row that patches BeamWeapon), the retained snapshot (BeamSettings '
            'rows by the production resolver) and the installed game data (package listings). No native reader of the '
            'beam firing path was traced, as for projectile sources; the live tests decide.'),
        'summary': summary, 'records': records, 'beamDeltas': patches,
        'beamTypes': {key: dict(row, consumers=sorted(consumers.get(int(key), [])),
            deltaConsumers=sorted(delta_consumers.get(int(key), []))) if row else None for key, row in sorted(
            rows.items(), key=lambda item: int(item[0]))}}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))
    for entry in report['records']:
        for owner in entry['owners']:
            print(entry['record'], entry['beamType'], entry['fireModeName'], owner['name'] or owner['path'] or
                owner['resource'], owner['kind'], owner['status'], [p['key'] for p in owner['packages']])


if __name__ == '__main__':
    main()
