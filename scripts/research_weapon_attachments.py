"""Map every weapon customization item (all slots) to its native effects. Read-only metadata research.

For each WeaponCustomizableItem in the pinned customization settings table:
  * slot(s) from the item row (WeaponCustomizationSlot, names checked against type-library lengths);
  * the entity delta keyed by its AddPath: every patched component (named natively by component index)
    and offset, with decoded WeaponDataComponent stat modifiers (type names checked against the type
    library) and reference labels for a reviewed set of offsets;
  * weapons whose resource default names it (per slot) and weapons whose unlock list names it
    (research/attachment-unlock-lists-F5FEE03DCFDB.json).
Nothing here is writable; magazine attachments are authored through MagazineAttachmentCapabilities.json.

Output: research/weapon-attachments-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
from research_booster_authoring import TypeLibrary
from research_magazine_attachments import (DATALIB, DELTAS_SHA, MODIFIERS, MODIFIER_COUNT, MODIFIER_STRIDE,
    customization_items, entity_deltas, native_layout, sha)

OUTPUT = ROOT / 'research/weapon-attachments-F5FEE03DCFDB.json'
UNLOCK_LISTS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
PLAYER = ROOT / 'schemas/player_weapon_authoring_catalog.json'
SLOT_ENUM = 'WeaponCustomizationSlot'
# Reference labels for reviewed offsets (Filediver datalibrary struct definitions, offsets checked against
# the pinned type library layouts by this script).
LABELS = {
    ('WeaponCustomizationComponentData', 120): 'optics unit',
    ('WeaponCustomizationComponentData', 128): 'magazine unit',
    ('WeaponCustomizationComponentData', 160): 'muzzle unit',
    ('WeaponCustomizationComponentData', 168): 'optics crosshair parameters',
    ('WeaponCustomizationComponentData', 192): 'underbarrel entity',
    ('WeaponCustomizationComponentData', 4736): 'magazine adjusting nodes',
    ('WeaponReloadComponentData', 56): 'reload duration',
    ('ProjectileWeaponComponentData', 0): 'projectile type selector',
    ('WeaponRoundsComponentData', 64): 'feed 1 projectile type selector',
    ('WeaponRoundsComponentData', 68): 'feed 2 projectile type selector',
}
RANGES = [(('WeaponCustomizationComponentData', 200, 4680), 'material overrides'),
    (('WeaponCustomizationComponentData', 4680, 4732), 'trigger settings'),
    (('WeaponDataComponentData', MODIFIERS, MODIFIERS + MODIFIER_STRIDE * MODIFIER_COUNT), 'stat modifiers')]
MAGAZINE_FIELDS = {('WeaponMagazineComponentData', offset): name for offset, name in
    ((136, 'capacity'), (140, 'starting magazines'), (144, 'magazines from supply'), (148, 'spare magazines'))}


def label(component, offset):
    if (component, offset) in LABELS:
        return LABELS[(component, offset)]
    if (component, offset) in MAGAZINE_FIELDS:
        return MAGAZINE_FIELDS[(component, offset)]
    for (name, low, high), text in RANGES:
        if component == name and low <= offset < high:
            return text
    return None


def slot_names(native):
    lengths = TypeLibrary(native.typelib, native.probe).lengths(SLOT_ENUM)
    text = (entity_research.FILEDIVER / 'datalibrary/enum/weaponcustomizationslot.go').read_text(encoding='utf-8')
    names = re.findall(r'^\s*' + SLOT_ENUM + r'_([A-Za-z0-9_]+)', text, re.M)
    if len(names) != len(lengths) or any(len(SLOT_ENUM + '_' + names[v]) != lengths[v] for v in lengths):
        raise ValueError('WeaponCustomizationSlot names disagree with the type library')
    return dict(enumerate(names))


def component_names(native, indices):
    result = {}
    for name in sorted(set(native.names.values())):
        if not name.endswith('ComponentData'):
            continue
        try:
            found = native.probe.find_component(native.entities, name)
        except Exception:
            continue
        index = struct.unpack_from('<I', native.entities, found[4] - 4)[0]
        if index in indices:
            if index in result and result[index] != name:
                raise ValueError(f'component index {index} is ambiguous')
            result[index] = name
    missing = sorted(set(indices) - set(result))
    if missing:
        raise ValueError('unnamed delta component indices: ' + ', '.join(map(str, missing)))
    return result


def main():
    native, modifier_names = native_layout()
    layouts = {'WeaponCustomizationComponent': {m['offset64'] for m in native.typelib_module.layout(
        native.typelib, 'WeaponCustomizationComponent', structured=True)['members']}}
    for (component, offset) in LABELS:
        if component == 'WeaponCustomizationComponentData' and offset not in layouts['WeaponCustomizationComponent']:
            raise ValueError(f'WeaponCustomizationComponent has no member at +{offset}')
    slots = slot_names(native)
    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    custom = (DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes()
    items = customization_items(custom)
    deltas, _ = entity_deltas(deltas_file)
    names = component_names(native, {entry['component'] for item in items
        for entry in (deltas.get(item['addPath']) or {'entries': []})['entries']})

    # Resource defaults per slot, from each player weapon's WeaponCustomizationComponentData.
    owners = native.owners('WeaponCustomizationComponentData')
    record_of = collections.defaultdict(list)
    for record, resources in owners.items():
        for resource in resources:
            record_of[resource].append(record)
    default_of = collections.defaultdict(set)
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        for resource in weapon['resources']:
            for record in record_of.get(int(resource, 16), []):
                body = native.record('WeaponCustomizationComponentData', record)
                for at in range(0, 80, 8):
                    slot, option = struct.unpack_from('<II', body, at)
                    if slot:
                        default_of[option].add(weapon['name'])
    listed_for = collections.defaultdict(set)
    for weapon in json.loads(UNLOCK_LISTS.read_text())['weapons']:
        for option in weapon['options']:
            listed_for[int(option['optionId'], 16)].add(weapon['weapon'])

    result = []
    for item in items:
        delta = deltas.get(item['addPath'])
        patched, modifiers = [], []
        words = {}
        for entry in (delta or {'entries': []})['entries']:
            component = names[entry['component']]
            patched.append({'component': component, 'offset': entry['offset'], 'size': entry['size'],
                'label': label(component, entry['offset'])})
            if component == 'WeaponDataComponentData' and MODIFIERS <= entry['offset'] < MODIFIERS + 64:
                for at in range(0, entry['size'], 4):
                    words[entry['offset'] + at] = entry['bytes'][at:at + 4]
        for index in range(MODIFIER_COUNT):
            kind = words.get(MODIFIERS + MODIFIER_STRIDE * index)
            value = words.get(MODIFIERS + MODIFIER_STRIDE * index + 4)
            if kind is None:
                continue
            kind = struct.unpack('<I', kind)[0]
            if modifier_names.get(kind) == 'Count':
                break
            modifiers.append({'type': modifier_names[kind],
                'value': round(struct.unpack('<f', value)[0], 6) if value else None})
        result.append({'debugName': item['debugName'], 'optionId': f"0x{item['optionId']:08X}",
            'addPath': f"0x{item['addPath']:016X}", 'slots': [slots[s] for s in item['slots']],
            'hasDelta': delta is not None, 'patched': patched, 'statModifiers': modifiers,
            'nativeDefaultOf': sorted(default_of.get(item['optionId'], ())),
            'unlockListedFor': sorted(listed_for.get(item['optionId'], ()))})
    OUTPUT.write_text(json.dumps({'schemaVersion': 1, 'customizationSettingsSha256': sha(custom),
        'entityDeltasSha256': DELTAS_SHA, 'slots': {str(k): v for k, v in slots.items()},
        'components': {str(k): v for k, v in sorted(names.items())}, 'items': result}, indent=1) + '\n', newline='\n')
    print(json.dumps({'items': len(result), 'bySlot': collections.Counter(s for r in result for s in r['slots']),
        'components': names}, indent=1, default=str))


if __name__ == '__main__':
    main()
