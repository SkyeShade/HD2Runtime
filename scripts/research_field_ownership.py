"""Which definition owns the effective gameplay value of each component-backed weapon field. Read-only research.

The Liberator projectile showed that a guarded write can land on a definition the game does not use: a weapon is built
from its entity components plus the entity deltas of its customization items, and a delta that patches a member
overwrites whatever the base component holds. The same can happen to any component field. For every catalogued
component-backed field of every player weapon (and every support weapon and backpack), this decodes:

- the weapon's default customization items and the entity deltas they apply at weapon build;
- the options its runtime unlock list lets the player equip instead (magazines, heatsinks, ...), and their deltas;
- every delta entry that patches bytes of the field's component member.

Classification per field instance:

  ACTIVE_AT_INSTANTIATION  no default or equippable customization patches the member: a weapon built after the write
                           uses it (the Reprimand projectile control); whether an already-built weapon re-reads it is
                           not established.
  OVERRIDDEN               a default customization item patches the member at every build: the base member is not the
                           effective value (the Liberator projectile pattern). The effective value is the delta's.
  AMBIGUOUS                no default patches it, but an equippable option does: the effective value depends on the
                           player's selection.

Settings rows (projectile, damage, explosion, status) are not entity components and are never patched by entity
deltas; they are read when the projectile or explosion is used (ACTIVE_DIRECT, live-proven for projectile damage and
status rows). They are summarized, not re-audited.

Output: research/field-ownership-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_attack_outputs as attack_outputs  # noqa: E402
from research_magazine_attachments import DATALIB, DELTAS_SHA, customization_items, entity_deltas, sha  # noqa: E402

OUTPUT = ROOT / 'research/field-ownership-F5FEE03DCFDB.json'
UNLOCK_LISTS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
PLAYER = ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json'
SLOT_NAMES = {1: 'underbarrel', 2: 'optic', 3: 'paint', 4: 'muzzle', 5: 'magazine', 6: 'ammunition',
    7: 'alternate ammunition', 8: 'internal', 9: 'trigger'}


def component_names(native):
    """Entity delta component index -> component type name, from the entity table framing."""
    data, header, size = native.entities, native.probe.HEADER, native.probe.HEADER_SIZE
    names, position = {}, 0
    while position < len(data):
        _, _, _, _, length, _ = header.unpack_from(data, position)
        end = position + size + length
        if end == len(data):
            break
        if data[end + 4:end + 8] == b'LDLD':
            position = end
        elif data[end + 8:end + 12] == b'LDLD':
            index = struct.unpack_from('<I', data, end)[0]
            position = end + 4
            names[index] = native.names.get(struct.unpack_from('<I', data, position)[0])
        else:
            break
    return names


def patches(delta, names):
    return [(names.get(e['component']), e['offset'], e['size'], e['bytes']) for e in (delta or {}).get('entries', [])]


def decode(storage, raw):
    if storage == 'f32':
        return round(struct.unpack('<f', raw[:4])[0], 6)
    if storage in ('u32', 'enum'):
        return struct.unpack('<I', raw[:4])[0]
    if storage in ('u8', 'bool'):
        return raw[0]
    return raw.hex()


def defaults_of(native, resource, by_id):
    component = native.component(resource, 'WeaponCustomizationComponentData')
    if not component:
        return None
    body = native.record('WeaponCustomizationComponentData', component['record_index'])
    out = []
    for at in range(0, 80, 8):
        slot, option = struct.unpack_from('<II', body, at)
        if option in by_id:
            out.append((slot, by_id[option]))
    return out


def overlapping(field, entries):
    b = field['backing']
    start, end = b['offset'], b['offset'] + b['width']
    return [(component, offset, size, raw) for component, offset, size, raw in entries
        if component == b['component'] and offset < end and offset + size > start]


def value_in(field, component_patches):
    """The member value a delta writes (when one entry covers the whole member)."""
    b = field['backing']
    for _, offset, size, raw in component_patches:
        if offset <= b['offset'] and offset + size >= b['offset'] + b['width']:
            return decode(b['storage'], raw[b['offset'] - offset:b['offset'] - offset + b['width']])
    return None


def build():
    native = attack_outputs.entity_research.Native()
    names = component_names(native)
    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    items = customization_items((DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    deltas, _ = entity_deltas(deltas_file)
    by_id = {item['optionId']: item for item in items}
    by_add = {item['addPath']: item for item in items}
    unlock = {entry['weapon']: entry for entry in json.loads(UNLOCK_LISTS.read_text())['weapons'] if entry['weapon']}
    catalog = json.loads(PLAYER.read_text())

    weapons, fields_out = [], []
    counts = collections.Counter()
    for weapon in catalog['weapons']:
        if not weapon['resources']:
            continue
        resource = weapon['resources'][0]
        defaults = defaults_of(native, resource, by_id) or []
        default_paths = {item['addPath'] for _, item in defaults}
        default_patches = {item['debugName']: (slot, patches(deltas.get(item['addPath']), names)) for slot, item in defaults}
        listed = unlock.get(weapon['name'])
        equippable = {}
        for option in (listed or {}).get('options', []):
            path = int(option['addPath'], 16)
            if path in default_paths or path not in by_add:
                continue
            equippable[by_add[path]['debugName']] = (by_add[path]['slots'], patches(deltas.get(path), names))
        weapons.append({'weapon': weapon['name'], 'resolution': weapon['resolution'],
            'defaultCustomization': [{'slot': slot, 'slotName': SLOT_NAMES.get(slot), 'item': item['debugName'],
                'patchedMembers': sorted({f'{c}+{o}/{s}' for c, o, s, _ in default_patches[item['debugName']][1]})}
                for slot, item in defaults],
            'unlockList': listed is not None, 'equippableOptions': len(equippable)})
        for field in weapon['fields']:
            b = field.get('backing') or {}
            if b.get('kind') != 'component':
                continue
            row = {'weapon': weapon['name'], 'field': field['semanticFieldId'], 'editable': field['editable'],
                'member': f"{b['component'].removesuffix('ComponentData')} +{b['offset']}",
                'baseValue': field.get('currentDefault')}
            by_default = [(item, slot, overlapping(field, entries)) for item, (slot, entries) in default_patches.items()]
            by_default = [(item, slot, hit) for item, slot, hit in by_default if hit]
            by_option = [(item, slots, overlapping(field, entries)) for item, (slots, entries) in equippable.items()]
            by_option = [(item, slots, hit) for item, slots, hit in by_option if hit]
            if by_default:
                item, slot, hit = by_default[0]
                row.update(status='OVERRIDDEN', owner={'kind': 'default_customization', 'item': item, 'slot': slot,
                    'slotName': SLOT_NAMES.get(slot), 'effectiveValue': value_in(field, hit)},
                    overriddenBy=[i for i, _, _ in by_default])
            elif by_option:
                row.update(status='AMBIGUOUS', owner={'kind': 'equippable_customization',
                    'options': sorted(i for i, _, _ in by_option)[:12], 'optionCount': len(by_option)})
            else:
                row.update(status='ACTIVE_AT_INSTANTIATION', owner={'kind': 'component'})
            if by_default and by_option:
                row['alsoEquippable'] = len(by_option)
            counts[(row['status'], row['editable'])] += 1
            fields_out.append(row)

    # Support weapons and backpacks: entities without a customization component cannot be delta-patched.
    support = []
    for name, kind, resource in attack_outputs.weapons():
        if kind != 'support_weapon':
            continue
        defaults = defaults_of(native, resource, by_id)
        support.append({'weapon': name, 'customizationComponent': defaults is not None,
            'defaultPatchedMembers': sorted({f'{c}+{o}/{s}' for _, item in (defaults or [])
                for c, o, s, _ in patches(deltas.get(item['addPath']), names)})})
    summary = {'playerWeapons': len(weapons), 'componentFields': len(fields_out),
        'byStatus': dict(sorted(collections.Counter(r['status'] for r in fields_out).items())),
        'editableByStatus': dict(sorted(collections.Counter(r['status'] for r in fields_out if r['editable']).items())),
        'editableOverriddenByField': dict(sorted(collections.Counter(r['field'] for r in fields_out
            if r['editable'] and r['status'] == 'OVERRIDDEN').items())),
        'editableAmbiguousByField': dict(sorted(collections.Counter(r['field'] for r in fields_out
            if r['editable'] and r['status'] == 'AMBIGUOUS').items())),
        'supportWeaponsWithCustomization': sorted(s['weapon'] for s in support if s['customizationComponent'])}
    return {'schemaVersion': 1, 'writes': 0, 'fixtureFallback': 'disabled', 'build': 'F5FEE03DCFDB',
        'model': __doc__.split('Output:')[0].strip(), 'summary': summary, 'weapons': weapons, 'supportWeapons': support,
        'fields': fields_out}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
