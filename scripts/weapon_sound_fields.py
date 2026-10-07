"""Shared helper for the weapon firing-sound field `weapon.sound` (player and support weapon catalogs).

Source: research/weapon-sounds-F5FEE03DCFDB.json (scripts/research_weapon_sounds.py; docs/research/
weapon-sounds-F5FEE03DCFDB.md) and the catalogue names of scripts/generate_weapon_sounds.py.

A weapon's firing sound is its resolved ProjectileWeapon record's events: the per-shot event +0x104 (260; +0x10C in
fire mode 4 and +0x110 in fire mode 7 when set), MIDI notes when +0xED (237) is set, or a loop (+0xFC 252 start,
+0x100 256 stop) on the fire decision's edges. The field writes the weapon type's record (the template a weapon is
built from) exactly as a catalogue entry's chin-turret writes do, relative to this weapon's own values:

  a shot:  +252 = 0, +256 = 0, +260 = the entry's event, +237 = the entry's MIDI flag;
  a loop:  +252 = start, +256 = stop, +260 = 0, +237 = 0.

The value is a catalogue sound name ('support/mg206', 'sentry/gatling'); `expect` is the weapon's own catalogued
sound (the reviewed baseline: its type's sound as built, a folded type's being the entry it was folded into).

Refused (the field is published read-only with the reason, or as a blocked declaration):
- no ProjectileWeapon record / the type posts no catalogued sound;
- fire mode 4 or 7 in any of the weapon's fire-mode slots (those modes post +0x10C / +0x110 when set);
- suppressed (WeaponData +112) or silenced-switched (+0x22C, which selects the silenced events +0x210..+0x218);
- a WeaponData event-override table (+0x410) is set (unmapped: whether it replaces the firing sound is unproven);
- a default customization item patches the sound members (the base record is not what the weapon is built with).
"""
from __future__ import annotations

import json
from pathlib import Path

import generate_weapon_sounds

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/weapon-sounds-F5FEE03DCFDB.json'
OWNERSHIP = ROOT / 'research/field-ownership-F5FEE03DCFDB.json'
FIELD = 'weapon.sound'
COMPONENT = 'ProjectileWeaponComponentData'
OFFSET, WIDTH, MIDI_OFFSET = 252, 12, 237
STORAGE = 'weapon_sound'
# The sound members a write touches (component offset, size): the MIDI flag and the loop start / stop / per-shot block.
MEMBERS = ((MIDI_OFFSET, 1), (OFFSET, WIDTH))
UNVERIFIED = ('ProjectileWeapon +237 (MIDI), +252/+256 (loop start/stop) and +260 (per-shot event) are the members '
    'the weapon fire path reads its firing sound from (game.dll, research/weapon-sounds); taking a catalogue sound on '
    'a per-entity copy is offline-proven (Pelican chin turret) and copying +260 is live-proven by the weapon clone, but '
    'a template sound write on a player or support weapon has not been live-tested.')
EFFECT = ('A component member the game copies into the weapon when it builds it: weapons built after the write post '
    'the new sound; a weapon already built keeps its copy until it is rebuilt (redeploy, reinforce, re-equip, a new '
    'call-in). Only this game plays it: every machine reads the events from its own copy of the record.')


NO_RECORD = ('The weapon has no ProjectileWeapon record (a beam, arc, spray, melee, thrown or placed weapon): its firing sound '
    'is not a ProjectileWeapon event this field can write.')


def key(resource: str) -> str:
    """A catalog resource hash ('0xA8A9...') as the research keys it ('A8A9...')."""
    return resource.upper().removeprefix('0X')


def _hex_le(value: str) -> str:
    """A big-endian event id ('9DCF5F6B') as its little-endian record bytes."""
    return int(value, 16).to_bytes(4, 'little').hex()


def load():
    """(entries by resource, silent type resources, sound names by resource, catalogue entries)."""
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    entries = {entry['resource']: entry for entry in research['entries']}
    sounds = generate_weapon_sounds.build()['sounds']
    return {'entries': entries, 'silent': set(research['silentTypes']), 'missing': set(research['notCatalogued']),
        'names': generate_weapon_sounds.names_by_resource(), 'sounds': sounds,
        'ownership': json.loads(OWNERSHIP.read_text(encoding='utf-8'))}


def _support_default_patch(data, weapon):
    for row in data['ownership']['supportWeapons']:
        if row['weapon'] != weapon:
            continue
        for member in row['defaultPatchedMembers']:
            component, rest = member.split('+')
            offset, size = (int(v) for v in rest.split('/'))
            if component == COMPONENT and any(offset < o + s and o < offset + size for o, s in MEMBERS):
                return member
    return None


def _player_ownership(data, weapon):
    for row in data['ownership']['fields']:
        if row['weapon'] == weapon and row['field'] == FIELD:
            return row
    return None


def refusal(data, kind, weapon, resource, fire_row, suppressed):
    """The reason weapon.sound is refused on this weapon, or None."""
    resource = key(resource)
    if resource in data['silent']:
        return ('The weapon\'s ProjectileWeapon type posts no firing sound (every sound member is 0): there is no '
            'catalogued baseline to replace or restore.')
    if resource in data['missing']:
        return 'The weapon\'s firing sound is in no Wwise bank of this build: it is not catalogued.'
    entry = data['entries'].get(resource)
    if not entry:
        return 'The weapon\'s ProjectileWeapon type is not in the firing-sound research.'
    slots = (fire_row or {}).get('slots') or []
    modes = sorted({mode for mode in [entry['fireMode'], *slots] if mode in (4, 7)})
    record = entry['record']
    if modes or record['singleMode4'] != '00000000' or record['singleMode7'] != '00000000':
        return ('Fire mode ' + ' / '.join(str(m) for m in modes or (4, 7)) + ' selects another per-shot event '
            '(ProjectileWeapon +268 in mode 4, +272 in mode 7 when set) that this field does not write.')
    silenced = entry['silenced']
    if suppressed or silenced['silenced'] or any(silenced[k] != '00000000' for k in
            ('silencedLoopStart', 'silencedLoopStop', 'silencedSingle')):
        return ('The weapon is suppressed or silenced-switched (WeaponData +112 / ProjectileWeapon +556): it posts '
            'the silenced events (+528 / +532 / +536), which this field does not write.')
    if entry['overrideEvents']:
        return ('The weapon\'s WeaponData event-override table (+1040) is set; whether it replaces the firing sound '
            'is not mapped.')
    if kind == 'support':
        member = _support_default_patch(data, weapon)
        if member:
            return 'A default customization item patches the sound members (' + member + ').'
    else:
        row = _player_ownership(data, weapon)
        if row and row['status'] == 'OVERRIDDEN':
            return ('A default customization item (' + ', '.join(row.get('overriddenBy') or []) + ') patches the '
                'sound members when the weapon is built.')
    if resource not in data['names']:
        return 'The weapon\'s firing sound has no catalogue name.'
    return None


def apply(field, data, kind, weapon, resource, fire_row, suppressed):
    """Complete a make_field result for weapon.sound on the ProjectileWeapon record of `resource`."""
    reason = refusal(data, kind, weapon, resource, fire_row, suppressed)
    resource = key(resource)
    entry = data['entries'].get(resource)
    name = data['names'].get(resource)
    if entry and name:
        record = entry['record']
        # The reviewed baseline: the type's own +252..+263 block and +237 flag, exactly as stored.
        field['currentDefault'] = name
        field['nativeSound'] = {'block': _hex_le(record['loopStart']) + _hex_le(record['loopStop'])
            + _hex_le(record['single']), 'midi': record['midi'], 'kind': entry['sound']['kind']}
    field['midiOffset'] = MIDI_OFFSET
    field['companionMembers'] = [[MIDI_OFFSET, 1]]
    if field.get('backing'):
        field['backing']['width'] = WIDTH
    ok = reason is None and field.get('editable', True)
    field['editable'] = field['acceptedForWrites'] = ok
    field['reason'] = None if ok else reason or field.get('reason')
    field['acknowledgement'] = 'allow_unverified_effect'
    field['acknowledgementReason'] = UNVERIFIED
    field['sound'] = {'catalogue': 'sdk/WeaponSoundCatalogue.json', 'values': 'hd2.sounds.list() names (kind shot or '
        'loop); resident-only sounds are refused, any other loads its bank package first',
        'restoreWithoutAcknowledgement': True}
    effect = {'activeSource': 'ACTIVE_AT_INSTANTIATION', 'appliesWhen': 'weapon_build', 'instantiationOnly': True,
        'activeSourceProven': True, 'reason': EFFECT, 'writeVerifiedOnApply': ok, 'gameplayEffectProven': False,
        'unverifiedEffect': True}
    row = _player_ownership(data, weapon) if kind == 'player' else None
    if row and row['status'] == 'AMBIGUOUS':
        options = row['owner']['options']
        effect.update(activeSource='AMBIGUOUS', activeSourceProven=False, overriddenWhenEquipped=options,
            reason='Equipping ' + ', '.join(options) + ' overwrites the sound members at weapon build; the sound '
                'applies while an option that does not patch them is equipped. ' + EFFECT)
    field['effect'] = effect
    field['evidence'] = {'source': 'research/weapon-sounds-F5FEE03DCFDB.json', 'gameplayProven': False,
        'nativeOwner': 'ProjectileWeaponComponent firing-sound events (+237 MIDI, +252 loop start, +256 loop stop, '
            '+260 per-shot event)'}
    return field
