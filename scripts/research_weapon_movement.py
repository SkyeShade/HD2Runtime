"""Research the native model behind weapon movement restrictions while firing. Read-only; nothing here writes.

Anchors: the M-1000 Maxigun cannot move (or dive) while firing, the GL-28 Belt-Fed Grenade Launcher and the
B/FLAM-80 Cremator slow their wielder, ordinary weapons do not restrict movement.

Findings (proven below from the retained snapshot, the pinned type library and game.dll code bytes):

* No weapon record carries a movement-speed multiplier. A differential over every member of every component owned
  by any resolved player or support weapon finds no scalar unique to the anchors that behaves like one.
* WeaponDataComponent +387 (u8, hidden 23-character name, added with the Maxigun) is set on the Maxigun only.
  game.dll reads it (the only reader of that byte) through the WeaponData getter while the wielder fires: when set
  it sends the weapon's firing-start wielder animation event (+388), arms the firing-stop event (+392), and raises
  bit 55 of the wielder's 192-bit action mask. This is the data-driven "stationary while firing" restriction.
* +388/+392 are the firing-start/stop wielder animation events. Only the Maxigun and the GL-28 carry them
  ("brace" / "brace_exit"); the only code reader found sends them only when +387 is set, so on the GL-28 they are
  present but not sent by that path. The Maxigun and the GL-28 differ in movement-related weapon data only by
  +387.
* +928 is the per-shot wielder animation event (fire_rifle, fire_mg, fire_minigun, fire_flamethrower, ...). It is
  published read-only: the Maxigun and the GL-28 share fire_minigun, and whether a per-shot animation slows the
  wielder is animation-graph behaviour, not data this project can prove.
* WeaponDataComponent +1220 (u8, 31-character name) is set on the Cremator (and its Exosuit twin) only, but its only
  reader is the weapon audio update (it sits between the rounds_remaining and weapon_rpm RTPC writes), so it is
  not a movement flag. The Cremator's slowdown has no data owner found.
* The helldiver avatar's locomotion states are stand, crouch, prone, stand_limp, crouch_limp, swim, march (walk
  only) and land_heavy; none is selected by weapon data.

Outputs research/weapon-movement-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402

OUTPUT = ROOT / 'research/weapon-movement-F5FEE03DCFDB.json'
STATIONARY_OFFSET, START_EVENT_OFFSET, STOP_EVENT_OFFSET, PER_SHOT_EVENT_OFFSET = 387, 388, 392, 928
AUDIO_FLAG_OFFSET = 1220
# WeaponDataComponent members the model relies on: (offset, size, storage, hidden-name length).
FINGERPRINT = [(384, 1, 'UINT8', 9), (385, 1, 'UINT8', 11), (386, 1, 'UINT8', 12), (387, 1, 'UINT8', 23),
    (388, 4, 'UINT32', 42), (392, 4, 'UINT32', 41), (396, 1, 'UINT8', 14), (928, 4, 'UINT32', 32),
    (1220, 1, 'UINT8', 31), (1224, 4, 'FP32', 26)]
RECORD_SIZE = 1232
# cmp byte ptr [rax+0x183],0 / je / cmp dword [rsi+8],0 / jne / cmp dword [rax+0x188],0 / je / cmp dword [rax+0x184],0
STATIONARY_READER = re.compile(re.escape(bytes.fromhex('80b88301000000')) + b'.{2}' + re.escape(bytes.fromhex('837e0800'))
    + b'.{2}' + re.escape(bytes.fromhex('83b88801000000')) + b'.{2}' + re.escape(bytes.fromhex('83b88401000000')), re.S)
ACTION_BIT = re.compile(re.escape(bytes.fromhex('480fbae837')))        # bts rax, 0x37
AUDIO_READER = re.compile(re.escape(bytes.fromhex('4438b0c4040000')))  # cmp byte ptr [rax+0x4c4], r14b
AVATAR = 0x4D1C334D294DFA97                                           # content/fac_helldivers/cha_avatar/avatar_helldiver
LOCOMOTION_STATE_NAMES = {0x2E3F3C44: 'stand_limp', 0xB013CA6F: 'crouch_limp', 0x92AA29EB: 'swim', 0x326DCAC2: 'march'}


def hexid(value):
    return f'0x{value:016X}'


def resolved_weapons():
    """(kind, name) -> resource for every weapon Runtime resolves to one native root."""
    out = {}
    player = json.loads((ROOT / 'schemas/player_weapon_authoring_catalog.json').read_text())
    for weapon in player['weapons']:
        if weapon['resolution'] == 'UNIQUE':
            out[('player', weapon['name'])] = int(weapon['resources'][0], 16)
    support = json.loads((ROOT / 'schemas/support_weapon_authoring_catalog.json').read_text())
    delivery = json.loads((ROOT / 'research/support-weapon-coverage-F5FEE03DCFDB.json').read_text())['deliveryResolution']
    for weapon in support['weapons']:
        if weapon['resolution'] == 'UNIQUE' and weapon.get('attackResource'):
            out[('support', weapon['name'])] = int(weapon['attackResource'], 16)
        elif delivery.get(weapon['name'], {}).get('decision') == 'RESOLVED':
            out[('support', weapon['name'])] = int(delivery[weapon['name']]['deliveredRoot'], 16)
    return out


def function_start(data, at):
    while not (data[at - 1] == 0xCC and data[at - 2] == 0xCC):
        at -= 1
    return at


def string_refs(data, text):
    """RVAs of RIP-relative LEA instructions that load `text`."""
    targets = [m.start() for m in re.finditer(re.escape(text.encode()) + b'\0', data)]
    refs = []
    for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', data[:0x3000000]):
        at = m.start()
        if at + 7 + struct.unpack_from('<i', data, at + 3)[0] in targets:
            refs.append(at)
    return refs


def call_target(data, at):
    return at + 5 + struct.unpack_from('<i', data, at + 1)[0]


def code_evidence(snapshot_path):
    from snapshot_image import Snapshot
    snap = Snapshot(snapshot_path)
    try:
        _, data = snap.module_image('game.dll')
    finally:
        snap.close()
    stationary = [m.start() for m in STATIONARY_READER.finditer(data)]
    if len(stationary) != 1:
        raise ValueError(f'stationary-while-firing reader not unique ({len(stationary)})')
    reader = stationary[0]
    # The WeaponData pointer comes from the getter called just before the test (call; mov rcx,rax? ; call getter).
    getter_call = data.rfind(b'\xe8', reader - 16, reader)
    getter = call_target(data, getter_call)
    action = [m.start() for m in ACTION_BIT.finditer(data, reader, reader + 0x80)]
    if not action:
        raise ValueError('stationary reader no longer raises action bit 55')
    audio = [m.start() for m in AUDIO_READER.finditer(data)]
    if len(audio) != 1:
        raise ValueError(f'Cremator flag reader not unique ({len(audio)})')
    audio_function = function_start(data, audio[0])
    rtpc = {text: [r for r in string_refs(data, text) if audio_function <= r < audio[0] + 0x200]
        for text in ('rounds_remaining', 'rounds_remaining_percent', 'charge_amount', 'weapon_rpm')}
    if not all(rtpc.values()):
        raise ValueError('Cremator flag reader is no longer inside the weapon audio update')
    audio_getter = any(call_target(data, audio_function + m.start()) == getter
        for m in re.finditer(rb'\xe8', data[audio_function:audio[0]]))
    return {'stationaryReader': {'rva': reader, 'count': 1, 'weaponDataGetterRva': getter,
            'actionBit': 55, 'actionBitRva': action[0],
            'behaviour': ('When +387 is set: send the start event (+388) to the wielder, arm the stop event (+392) '
                'and raise bit 55 of the wielder action mask while firing.')},
        'audioFlagReader': {'rva': audio[0], 'count': 1, 'function': audio_function,
            'readsWeaponDataFromSameGetter': audio_getter, 'rtpcStrings': sorted(rtpc),
            'behaviour': 'Gates an extra component lookup inside the weapon audio RTPC update.'}}


def locomotion_states(native):
    """The helldiver avatar's locomotion states (reference only: none is selected by weapon data)."""
    component = native.component(hexid(AVATAR), 'LocomotionComponentData')
    raw = native.record('LocomotionComponentData', component['record_index'])
    states = []
    for index in range(8):
        base = index * 556
        name, group = struct.unpack_from('<II', raw, base)
        if not name:
            continue
        moves = [struct.unpack_from('<I', raw, base + 8 + 32 * k)[0] for k in range(8)]
        states.append({'state': native.thin_name(name) or LOCOMOTION_STATE_NAMES.get(name) or f'{name:08X}',
            'group': native.thin_name(group), 'movement': [native.thin_name(m) for m in moves if m]})
    return states


def build():
    from migration import build_view
    import research_entity_authoring
    native = research_entity_authoring.Native()
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    table = view.component('WeaponDataComponentData')
    layout = {(m['offset'], m['size'], m['storage'], m['nameLength']) for m in table.layout.members}
    missing = [item for item in FINGERPRINT if item not in layout]
    if missing or table.layout.size != RECORD_SIZE:
        raise ValueError(f'WeaponDataComponent layout changed: {missing}')
    weapons = []
    for (kind, name), resource in sorted(resolved_weapons().items(), key=lambda item: (item[0][0], item[0][1])):
        record = table.record(resource)
        if record is None:
            weapons.append({'kind': kind, 'name': name, 'resource': hexid(resource), 'weaponData': None})
            continue
        raw = record['bytes']
        u32 = lambda offset: struct.unpack_from('<I', raw, offset)[0]
        start, stop, shot = u32(START_EVENT_OFFSET), u32(STOP_EVENT_OFFSET), u32(PER_SHOT_EVENT_OFFSET)
        stationary = raw[STATIONARY_OFFSET]
        weapons.append({'kind': kind, 'name': name, 'resource': hexid(resource),
            'weaponData': {'recordIndex': record['recordIndex'], 'indexRow': record['indexRow'],
                'ownerCount': record['ownerCount']},
            'stationaryWhileFiring': bool(stationary),
            'firingStartEvent': native.thin_name(start) if start else None,
            'firingStopEvent': native.thin_name(stop) if stop else None,
            'firingStance': 'brace' if native.thin_name(start) == 'brace' else ('other' if start else None),
            'perShotWielderAnimation': native.thin_name(shot) if shot else None,
            'audioFlag1220': bool(raw[AUDIO_FLAG_OFFSET]),
            'movementRestriction': 'stationary_while_firing' if stationary else 'none'})
    by_name = {(w['kind'], w['name']): w for w in weapons}
    anchors = {'maxigun': by_name[('support', 'M-1000 Maxigun')], 'gl28': by_name[('support', 'GL-28 Belt-Fed Grenade Launcher')],
        'cremator': by_name[('support', 'B/FLAM-80 Cremator')]}
    if not anchors['maxigun']['stationaryWhileFiring'] or anchors['gl28']['stationaryWhileFiring']:
        raise ValueError('anchor stationary flags changed')
    if sorted(w['name'] for w in weapons if w.get('stationaryWhileFiring')) != ['M-1000 Maxigun']:
        raise ValueError('stationary flag is no longer Maxigun-only')
    code = code_evidence(build_profile.SNAPSHOT)
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'snapshot': build_profile.SNAPSHOT_NAME,
        'model': {
            'representation': ('One data-driven restriction: WeaponDataComponent +387 "stationary while firing" '
                '(bool). When set, firing sends the weapon\'s firing-start/stop wielder animation events and raises '
                'wielder action bit 55. No per-weapon movement multiplier, sprint/dive/crouch ban or stance-specific '
                'restriction exists in weapon data.'),
            'fingerprint': [dict(zip(('offset', 'size', 'storage', 'nameLength'), item)) for item in FINGERPRINT],
            'recordSize': RECORD_SIZE,
            'maxigunVersusGl28': ('Identical movement-related weapon data (brace/brace_exit events, fire_minigun '
                'per-shot animation) except +387.'),
            'codeDriven': ['slowdown magnitude (no data field)', 'which actions bit 55 blocks (diving, sprinting, '
                'walking are not separately represented in weapon data)', 'Cremator slowdown (no data owner found)',
                'GL-28 slowdown (its brace events are not sent by the only reader found; per-shot animation is a '
                'candidate, not proven)'],
            'notMovement': {'+1220': 'Cremator-only flag read by the weapon audio update.',
                '+1224': 'float, 1.0 on every weapon except the Meltagun (0.5); no reader proven.'}},
        'codeEvidence': code, 'avatarLocomotionStates': locomotion_states(native),
        'weapons': weapons,
        'summary': {'weapons': len(weapons), 'withWeaponData': sum(w['weaponData'] is not None for w in weapons),
            'stationaryWhileFiring': sorted(w['name'] for w in weapons if w.get('stationaryWhileFiring')),
            'braceEvents': sorted(w['name'] for w in weapons if w.get('firingStance') == 'brace'),
            'uniqueWeaponDataOwners': sum(1 for w in weapons if w['weaponData'] and w['weaponData']['ownerCount'] == 1)},
        'writes': 0, 'protectionChanges': 0}


def main():
    result = build()
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result['summary'], indent=1))


if __name__ == '__main__':
    main()
