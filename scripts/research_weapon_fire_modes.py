"""Map every player and support weapon's native fire-mode configuration. Read-only.

Native model (pinned type library, WeaponDataComponent, one uniquely owned record per weapon):

  +140  num_burst_rounds     UINT32         rounds per burst (weapon-wide)
  +144  primary_fire_mode    FireMode       the default mode
  +148  secondary_fire_mode  FireMode       } further selectable modes, packed in order;
  +152  tertiary_fire_mode   FireMode       } 0 (None) marks an empty slot
  +156  quaternary_fire_mode FireMode       }
  +160  24-byte struct                      set only on a few special weapons
  +184  function_info {left, right}         WeaponFunctionType bound to each input; Firemode (3)
                                            is the in-game fire-mode selector
  +1040 weapon_function_fire_modes[8]       per-function fire-mode entries (20 bytes each)

Fire modes are therefore a fixed four-slot enum list, not flags or references. Rate of fire is one
value per weapon (ProjectileWeaponComponentData.rpm), shared by every mode. FireMode names are
published only where the type library alias length matches (None, Automatic, Single, Burst);
values 4-8 (charge and safety states) stay unnamed.

Output: research/weapon-fire-modes-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
from research_booster_authoring import TypeLibrary

OUTPUT = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
PLAYER = ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json'
SUPPORT = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
COMPONENT, RECORD = 'WeaponDataComponentData', 'WeaponDataComponent'
LAYOUT = {140: ('num_burst_rounds', 16, 'UINT32', None), 144: ('primary', 17, 'ENUM_UINT32', 'FireMode'),
    148: ('secondary', 19, 'ENUM_UINT32', 'FireMode'), 152: ('tertiary', 18, 'ENUM_UINT32', 'FireMode'),
    156: ('quaternary', 21, 'ENUM_UINT32', 'FireMode'), 184: ('function_info', 13, 'STRUCT', None)}
FUNCTION_TABLE, FUNCTION_STRIDE = 1040, 20
SPECIAL = (160, 184)
MODE_NAMES = {1: 'automatic', 2: 'single', 3: 'burst'}
FIREMODE_SELECTOR = 3
# Input functions that leave the trigger ordinary: none, the fire-mode selector, and a rate selector.
ORDINARY_FUNCTIONS = {0, 2, 3}
# Trigger families, from native component ownership (pinned entity library). Fire modes are authored
# only where an ordinary projectile trigger fires and no charge, wind-up, beam, arc, spray or melee
# component shapes the trigger.
FAMILY_COMPONENTS = {'ProjectileWeaponComponentData': 'conventional_projectile', 'WeaponRoundsComponentData': 'rounds_feed',
    'WeaponChargeComponentData': 'charge', 'WeaponWindUpComponentData': 'wind_up', 'BeamWeaponComponentData': 'beam',
    'ArcWeaponComponentData': 'arc', 'SprayWeaponComponentData': 'spray', 'MeleeWeaponComponentData': 'melee'}
CONVENTIONAL = {'conventional_projectile', 'rounds_feed'}
SPECIAL_TRIGGERS = {'charge', 'wind_up', 'beam', 'arc', 'spray', 'melee'}


def enum_names(native, enum):
    lengths = TypeLibrary(native.typelib, native.probe).lengths(enum)
    text = (entity_research.FILEDIVER / ('datalibrary/enum/' + enum.lower() + '.go')).read_text(encoding='utf-8')
    reference = re.findall(r'^\s*' + enum + r'_([A-Za-z0-9_]+)', text, re.M)
    return {value: reference[value] if value < len(reference) and len(enum + '_' + reference[value]) == length else None
        for value, length in lengths.items()}


def prove_layout(native):
    members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, RECORD, structured=True)['members']}
    for offset, (label, length, storage, enum) in LAYOUT.items():
        member = members[offset]
        if not member['name'].endswith(f'inferred_length={length}') or member['storage'] != storage:
            raise ValueError(f'{RECORD} +{offset} ({label}) changed')
        if enum and member['type_hash'] != native.probe.dl_hash(enum):
            raise ValueError(f'{RECORD} +{offset} is no longer {enum}')
    table = members[FUNCTION_TABLE]
    if table['array_or_bits'] != 8 or table['size64'] != 8 * FUNCTION_STRIDE:
        raise ValueError('weapon_function_fire_modes layout changed')
    info = native.typelib_module.layout(native.typelib, members[184]['type_hash'], structured=True)['members']
    if [(m['offset64'], m['type_hash']) for m in info] != [(0, native.probe.dl_hash('WeaponFunctionType')),
            (4, native.probe.dl_hash('WeaponFunctionType'))]:
        raise ValueError('WeaponFunctionInfo layout changed')


def weapons(native):
    owned = {}
    for component, family in FAMILY_COMPONENTS.items():
        for resources in native.owners(component).values():
            for resource in resources:
                owned.setdefault(resource, set()).add(family)

    def families(resources):
        return set().union(*(owned.get(int(r, 16), set()) for r in resources)) if resources else set()
    rows = []
    for weapon in json.loads(PLAYER.read_text())['weapons']:
        primary = next((f['currentDefault'] for f in weapon['fields'] if f['semanticFieldId'] == 'weapon.primary_fire_mode'), None)
        rows.append(('player', weapon['name'], weapon['resources'], families(weapon['resources']), primary))
    for weapon in json.loads(SUPPORT.read_text())['weapons']:
        identity = weapon['catalogIdentity']
        name = identity['name'] if isinstance(identity, dict) else identity
        rows.append(('support', name, weapon['resourceHashes'], families(weapon['resourceHashes']), None))
    return rows


def main():
    native = entity_research.Native()
    prove_layout(native)
    fire_names = enum_names(native, 'FireMode')
    function_names = enum_names(native, 'WeaponFunctionType')
    if [fire_names[v] for v in (0, 1, 2, 3)] != ['None', 'Automatic', 'Single', 'Burst']:
        raise ValueError('FireMode 0-3 no longer align with the type library')
    if function_names[FIREMODE_SELECTOR] != 'Firemode':
        raise ValueError('WeaponFunctionType 3 is no longer Firemode')
    owners = native.owners(COMPONENT)
    record_of = {}
    for record, resources in owners.items():
        for resource in resources:
            record_of.setdefault(resource, []).append(record)
    result = []
    for kind, name, resources, families, snapshot_primary in weapons(native):
        records = {}
        for resource in resources:
            found = record_of.get(int(resource, 16), [])
            if len(found) == 1:
                body = native.record(COMPONENT, found[0])
                functions = []
                for index in range(8):
                    function, first, second, mode, flag = struct.unpack_from('<IIIIB', body, FUNCTION_TABLE + FUNCTION_STRIDE * index)
                    if function or mode:
                        functions.append({'function': function_names.get(function) or function, 'fireMode': mode})
                left, right = struct.unpack_from('<2I', body, 184)
                records[resource] = {'record': found[0], 'owners': len(owners[found[0]]),
                    'burstRounds': struct.unpack_from('<I', body, 140)[0],
                    'slots': list(struct.unpack_from('<4I', body, 144)),
                    'special': body[SPECIAL[0]:SPECIAL[1]] != bytes(SPECIAL[1] - SPECIAL[0]),
                    'selector': {'left': function_names.get(left) or left, 'right': function_names.get(right) or right,
                        'leftValue': left, 'rightValue': right},
                    'functionTable': functions}
        shapes = {json.dumps({k: v for k, v in item.items() if k != 'record'}, sort_keys=True) for item in records.values()}
        row = {'kind': kind, 'weapon': name, 'families': sorted(families), 'roots': len(records)}
        if not records:
            row.update(state='absent', reason='The weapon owns no WeaponDataComponentData record.')
            result.append(row)
            continue
        if len(shapes) != 1:
            row.update(state='blocked', reason='The weapon roots disagree on their fire-mode configuration.')
            result.append(row)
            continue
        item = next(iter(records.values()))
        slots = item['slots']
        modes = [value for value in slots if value]
        packed = slots[:len(modes)] == modes
        selector = FIREMODE_SELECTOR in (item['selector']['leftValue'], item['selector']['rightValue'])
        row.update(slots=slots, modes=[MODE_NAMES.get(v) or fire_names.get(v) or v for v in modes],
            modeValues=modes, defaultMode=MODE_NAMES.get(modes[0]) if modes else None,
            burstRounds=item['burstRounds'], selector=item['selector'], selectorBound=selector,
            functionTable=item['functionTable'], specialStruct=item['special'],
            ownerUnique=all(r['owners'] == 1 for r in records.values()),
            snapshotPrimaryMatches=None if snapshot_primary is None else snapshot_primary == slots[0])
        if row['snapshotPrimaryMatches'] is False:
            raise ValueError(name + ': pinned primary fire mode differs from the snapshot catalog')
        def classify(families):
            if not modes or not packed:
                return 'blocked', 'The mode slots are empty or not packed.'
            if any(value not in MODE_NAMES for value in modes):
                return 'blocked', ('The weapon uses a charge or safety fire mode ('
                    + ', '.join(str(fire_names.get(v) or v) for v in modes if v not in MODE_NAMES)
                    + '); only Automatic, Single and Burst are proven.')
            if not families & CONVENTIONAL or families & SPECIAL_TRIGGERS:
                return 'blocked', ('Fire modes are authored only for conventional projectile weapons; this weapon '
                    'fires through ' + (', '.join(sorted(families)) or 'no projectile trigger') + '.')
            if item['special']:
                return 'blocked', 'The weapon carries a special fire-control structure (+160) whose semantics are unknown.'
            if not {item['selector']['leftValue'], item['selector']['rightValue']} <= ORDINARY_FUNCTIONS:
                special = [str(item['selector'][side]) for side in ('left', 'right')
                    if item['selector'][side + 'Value'] not in ORDINARY_FUNCTIONS]
                return 'blocked', ('The weapon binds ' + ', '.join(special) + ', which changes how its trigger '
                    'fires; fire modes are not authored on such weapons.')
            if item['functionTable']:
                return 'blocked', 'The weapon has weapon-function fire-mode entries whose semantics are unknown.'
            if not row['ownerUnique']:
                return 'blocked', 'The WeaponDataComponentData record is shared.'
            if selector:
                return 'selectable', None
            if len(modes) == 1:
                return 'single_mode', None
            return 'blocked', 'Several modes but no fire-mode selector is bound; the switching path is unknown.'
        state, reason = classify(families)
        row.update(state=state, reason=reason, maxModes=4 if state == 'selectable' else 1 if state == 'single_mode' else None)
        # A conventional projectile weapon whose only special trigger is a wind-up (WeaponWindUpComponentData, the
        # M-1000 Maxigun): the state its trigger would have without the wind-up. Fire modes stay blocked; the rate of
        # fire research (research_weapon_functions.py) opens its rate slots behind allow_unverified_effect.
        if families & SPECIAL_TRIGGERS == {'wind_up'} and families & CONVENTIONAL:
            row['windUp'] = {'stateWithoutWindUp': classify(families - {'wind_up'})[0]}
        result.append(row)
    report = {'schemaVersion': 1, 'typelibSha256': entity_research.TYPELIB_SHA256,
        'layout': {str(k): v[0] for k, v in LAYOUT.items()},
        'fireMode': {str(k): v for k, v in fire_names.items()},
        'weaponFunction': {str(k): v for k, v in function_names.items()},
        'semanticModes': MODE_NAMES,
        'model': {'modeSet': 'four packed FireMode slots at +144; slot 1 is the default mode',
            'burst': 'num_burst_rounds (+140), weapon-wide', 'fireRate': 'one ProjectileWeaponComponentData rpm shared by every mode',
            'selector': 'function_info binds WeaponFunctionType Firemode (3) to the left or right input'},
        'weapons': result}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    print(json.dumps({'states': Counter((r['kind'], r['state']) for r in result).most_common(),
        'fireMode': report['fireMode']}, indent=1, default=str))


if __name__ == '__main__':
    main()
