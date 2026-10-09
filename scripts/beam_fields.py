"""Beam outputs and beam swaps (0.30.4, research/beam-outputs-F5FEE03DCFDB.json; docs/attack-outputs.md "Beam swaps").

A beam is fired only by a BeamWeaponComponent: its +0 (typed BeamType) names the BeamSettings row the weapon fires. A
beam swap re-points that one reference on a weapon that already owns the component (no component is added: projectile
weapons stay projectile weapons). Like projectile swaps, the written member must be the weapon's active beam source:

- ACTIVE_DIRECT (component): no default or equippable customization patches BeamWeapon +0, so the weapon's own record
  +0 is what it fires: the field attack.beam on the weapon itself (LAS-13 Trident, LAS-7 Dagger, LAS-98, 40-K Meltagun,
  the A/LAS-98 Laser Sentry).
- INDIRECT (attachment): the default muzzle "Laser. Standard Prism" patches BeamWeapon +0 when the weapon is built, so
  the base member is dormant (the Liberator ammunition lesson). The swap writes that muzzle's delta row instead, through
  weapon:beam_source() (domains/attack_outputs.lua beamAttachments): the LAS-5 Scythe and the AX/LAS-5 Rover drone gun,
  which share it.

Used by the player, support and vehicle weapon generators (the attack.beam field of component hosts and the read-only
reason of attachment hosts) and by scripts/generate_attack_outputs.py (beam outputs, hosts and attachment sources).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/beam-outputs-F5FEE03DCFDB.json'
FIELD = 'attack.beam'
BEAM = 'BeamWeaponComponentData'
BEAM_INDEX = 270  # the BeamWeapon component index entity deltas name (proven by scripts/research_beam_outputs.py)
CLASSES = {4: 'continuous', 5: 'charged', 6: 'pulsed'}
UNVERIFIED = ('Re-points this weapon\'s BeamType (BeamWeapon +0): it fires the donor\'s BeamSettings row (length, radius, '
    'damage row, hit effects and beam visuals) with its own fire mode, rate, heat and sounds. The written member is the '
    'weapon\'s active beam source (research/beam-outputs-F5FEE03DCFDB.json: no customization delta patches it, or the '
    'patching delta row itself), but no beam swap has been shown in game yet.')
REFERENCE_REASON = ('Every beam donor other than the weapon\'s own beam is not live-tested: allow_unverified_reference '
    'and allow_unverified_effect are both required (restoring the weapon\'s own beam needs neither).')
DORMANT = ('DORMANT_BEAM_REFERENCE: the default customization item {item} patches BeamWeapon +0 when the weapon is built, '
    'so this member is dormant (the delta is the active beam source). Write the target weapon:beam_source() returns '
    '(the muzzle definition\'s beam, hd2.fields.attack.beam) instead.')
EFFECT = {'activeSource': 'ACTIVE_AT_INSTANTIATION', 'appliesWhen': 'weapon_build', 'instantiationOnly': True,
    'activeSourceProven': True, 'gameplayEffectProven': False, 'unverifiedEffect': True,
    'reason': ('A component member (or customization delta) the game applies when it builds the weapon: a weapon built '
        'after the write fires the new beam; one already in hand keeps its copy until it is rebuilt (re-equip, '
        'resupply or a new call-in).')}


@lru_cache(maxsize=1)
def research():
    data = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if data['writes'] != 0 or data['build'] != 'F5FEE03DCFDB':
        raise ValueError('unexpected beam output research')
    return data


def owner(resource):
    """(record, owner) of a BeamWeapon owner entity by its resource ('0x...'), or (None, None)."""
    value = int(resource, 16) if isinstance(resource, str) else resource
    for record in research()['records']:
        for item in record['owners']:
            if int(item['resource'], 16) == value:
                return record, item
    return None, None


def row(beam_type):
    """The BeamSettings row (identity, length, damage, resources) of a beam type."""
    item = research()['beamTypes'].get(str(beam_type))
    if not item:
        raise ValueError(f'beam type {beam_type} has no resolved BeamSettings row')
    return item


def active_type(record, item):
    """The BeamType the owner fires: the default customization delta's value when that delta is its proven active
    source (INDIRECT), its record +0 when nothing patches it (ACTIVE_DIRECT), else None (not proven)."""
    if item['status'] == 'INDIRECT':
        return item['activeSource']['value']
    return record['beamType'] if item['status'] == 'ACTIVE_DIRECT' else None


def reference_field(make, resource, key, backend, identity_check=None):
    """The attack.beam field of a beam weapon (its own BeamWeapon record), or None when it owns none.

    make(field_id, current, backing, editable, reason) builds the generator's own field shape. ACTIVE_DIRECT hosts get an
    editable component field; an INDIRECT host (its default muzzle patches +0) gets the same member read-only with the
    reason and the redirect to weapon:beam_source()."""
    record, item = owner(resource)
    if not record:
        return None
    identity = item['componentIdentity']
    backing = backend(0, 'u32')
    if identity_check is not None:
        identity_check(identity, backing)
    for name in ('recordIndex', 'indexRow', 'ownerCount'):
        if backing.get(name) != identity[name]:
            raise ValueError(f'{key}: BeamWeapon record identity diverged from research/beam-outputs ({name})')
    editable = item['status'] == 'ACTIVE_DIRECT' and identity['uniqueOwner']
    reason = None
    if item['status'] == 'INDIRECT':
        reason = DORMANT.format(item=item['activeSource']['item'])
    elif not editable:
        reason = item['reason']
    field = make(FIELD, {'weapon': key, 'beamType': record['beamType']}, backing, editable, reason)
    field.update({'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': UNVERIFIED,
        'referenceKind': 'beam', 'referenceSettings': row(record['beamType'])['settings'],
        'beamClass': CLASSES.get(record['fireMode']), 'effect': dict(EFFECT) if editable else {
            'activeSource': 'OVERRIDDEN' if item['status'] == 'INDIRECT' else 'AMBIGUOUS', 'appliesWhen': 'weapon_build',
            'instantiationOnly': True, 'activeSourceProven': item['status'] == 'INDIRECT', 'reason': reason,
            **({'overriddenBy': item['activeSource']['item']} if item['status'] == 'INDIRECT' else {})},
        'beamSource': {'status': item['status'], 'mechanism': 'component' if editable else
            'attachment' if item['status'] == 'INDIRECT' else None, 'member': 'BeamWeapon +0', 'reason': item['reason']}})
    return field
