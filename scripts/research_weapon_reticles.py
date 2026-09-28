"""Map the third-person reticle policy of every player and support weapon. Read-only.

Native owner (pinned type library): WeaponDataComponent member at +400 is ENUM_UINT32 of
CrosshairWeaponType with a 14-character member name (crosshair_type). Each weapon owns its own
WeaponDataComponentData record, so the value is weapon-local.

Member names: the type library stores each enum value's hidden alias length. The Filediver reference
list predates one inserted member; a name is published only where its alias length matches exactly,
and ReticleAmr's version-labelled export supplies the inserted member at value 3
(CrosshairDamageIndicatorOnly). Values whose length no reference name matches stay unnamed.

Reticle semantics (native value -> third-person reticle):
  CrosshairDamageIndicatorOnly (3)  hidden (APW-1 baseline; ReticleAmr confirmed 3 -> 4 shows the
                                    normal reticle and leaves scope/ADS unchanged)
  named weapon crosshair styles     shown
  Default, CrosshairNever, CrosshairAlways, None, unnamed values
                                    not mapped (read-only)

Output: research/weapon-reticles-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
from research_booster_authoring import TypeLibrary

OUTPUT = ROOT / 'research/weapon-reticles-F5FEE03DCFDB.json'
PLAYER = ROOT / 'schemas/player_weapon_authoring_catalog.json'
SUPPORT = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
RETICLE_AMR = entity_research.SIBLINGS / 'ReticleAmr'
COMPONENT, RECORD_TYPE, OFFSET = 'WeaponDataComponentData', 'WeaponDataComponent', 400
ENUM = 'CrosshairWeaponType'
HIDDEN = 'CrosshairDamageIndicatorOnly'
SHOWN_DEFAULT = 'AssaultRifle'
# Values that do not select a weapon crosshair style: their third-person effect is not mapped.
UNMAPPED = {'Default', 'CrosshairNever', 'CrosshairAlways', 'None', 'Count'}


def reference_names():
    """Filediver's CrosshairWeaponType members, in declaration order."""
    text = (entity_research.FILEDIVER / 'datalibrary/enum/crosshairweapontype.go').read_text(encoding='utf-8')
    return re.findall(r'^\s*' + ENUM + r'_([A-Za-z0-9_]+)', text, re.M)


def member_names(lengths):
    """Align the reference names with the type-library alias lengths; unmatched values stay None."""
    reference = [name for name in reference_names() if not name.startswith('Value_')]
    policy = (RETICLE_AMR / 'research/reticle-policy.md').read_text(encoding='utf-8')
    if HIDDEN not in policy:
        raise ValueError('ReticleAmr reticle policy no longer names ' + HIDDEN)
    names, at = {}, 0
    for value in sorted(lengths):
        if value == 3 and len(ENUM + '_' + HIDDEN) == lengths[value]:
            names[value] = HIDDEN  # inserted member, named by ReticleAmr's version-labelled export
            continue
        while at < len(reference) and len(ENUM + '_' + reference[at]) != lengths[value] and reference[at] in names.values():
            at += 1
        if at < len(reference) and len(ENUM + '_' + reference[at]) == lengths[value]:
            names[value] = reference[at]
            at += 1
        else:
            names[value] = None
    if names.get(3) != HIDDEN or names.get(4) != SHOWN_DEFAULT or names.get(max(lengths)) != 'Count':
        raise ValueError('CrosshairWeaponType names do not align with the type library')
    return names


def weapons():
    result = []
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        result.append(('player', weapon['name'], [int(r, 16) for r in weapon['resources']]))
    for weapon in json.loads(SUPPORT.read_text())['weapons']:
        identity = weapon['catalogIdentity']
        name = identity['name'] if isinstance(identity, dict) else identity
        result.append(('support', name, [int(r, 16) for r in weapon['resourceHashes']]))
    return result


def main():
    native = entity_research.Native()
    layout = native.typelib_module.layout(native.typelib, RECORD_TYPE, structured=True)
    member = next(m for m in layout['members'] if m['offset64'] == OFFSET)
    if not (member['storage'] == 'ENUM_UINT32' and member['type_hash'] == native.probe.dl_hash(ENUM)
            and member['name'].endswith('inferred_length=14') and member['size64'] == 4):
        raise ValueError('WeaponDataComponent +400 is no longer crosshair_type')
    lengths = TypeLibrary(native.typelib, native.probe).lengths(ENUM)
    names = member_names(lengths)

    owners = native.owners(COMPONENT)
    record_of = {}
    for record, resources in owners.items():
        for resource in resources:
            record_of.setdefault(resource, []).append(record)
    rows = []
    for kind, name, resources in weapons():
        values = {}
        for resource in resources:
            records = record_of.get(resource, [])
            if len(records) == 1:
                body = native.record(COMPONENT, records[0])
                values[f'0x{resource:016X}'] = {'record': records[0], 'shared': len(owners[records[0]]) > 1,
                    'value': struct.unpack_from('<I', body, OFFSET)[0]}
        distinct = {v['value'] for v in values.values()}
        value = distinct.pop() if len(distinct) == 1 else None
        label = names.get(value) if value is not None else None
        if not values:
            state, reason = 'absent', 'The weapon owns no WeaponDataComponentData record.'
        elif value is None:
            state, reason = 'read_only', 'The weapon roots disagree on crosshair_type.'
        elif label == HIDDEN:
            state, reason = 'hidden', None
        elif label is None or label in UNMAPPED:
            state, reason = 'read_only', (f'crosshair_type {value} ({label or "unnamed"}) does not select a weapon '
                'crosshair style; its third-person effect is not mapped.')
        else:
            state, reason = 'shown', None
        rows.append({'kind': kind, 'weapon': name, 'crosshairType': value, 'crosshairTypeName': label,
            'reticle': state, 'reason': reason, 'records': values})
    result = {'schemaVersion': 1, 'typelibSha256': entity_research.TYPELIB_SHA256,
        'field': {'component': COMPONENT, 'recordType': RECORD_TYPE, 'offset': OFFSET, 'storage': 'ENUM_UINT32',
            'enum': ENUM, 'memberNameLength': 14, 'memberName': 'crosshair_type'},
        'enum': {'values': len(lengths), 'names': {str(k): v for k, v in sorted(names.items())},
            'nameSources': ['Filediver datalibrary/enum/crosshairweapontype.go (alias-length aligned)',
                'ReticleAmr/research/reticle-policy.md (value 3)']},
        'encoding': {'hidden': 3, 'shownWhenBaselineHidden': 4},
        'gameplayEvidence': {'weapon': 'APW-1 Anti-Materiel Rifle', 'transition': [3, 4],
            'source': 'ReticleAmr/research/gameplay-confirmation-0.1.0.json',
            'observed': 'normal third-person reticle; scope and ADS unchanged'},
        'weapons': rows}
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', newline='\n')
    from collections import Counter
    print(json.dumps({'names': result['enum']['names'],
        'states': Counter((r['kind'], r['reticle']) for r in rows).most_common()}, indent=1, default=str))


if __name__ == '__main__':
    main()
