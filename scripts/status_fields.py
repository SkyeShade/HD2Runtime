"""Generalized DamageInfo status slots for the weapon generators (research: scripts/research_status_effects.py).

A DamageInfo row has four inline status slots ({StatusEffectType +44+8n, strength f32 +48+8n}), packed from slot 1.
Every weapon DamageInfo field group gets, per row:

- `status_<k>_type` for each used slot k: a status_reference whose value is a catalog semantic ID;
- `status_<k>_type` and `status_<k>_strength` for the first empty slot (the attachment slot), whose current
  value is 'none' / 0.

Only the first empty slot is offered, so a write can never leave a gap in the packing. Values are limited to the
catalog's attachable statuses (ones a mapped player-side attack already applies through a DamageInfo slot).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
POLICY = ROOT / 'schemas/status_attachment_policy.json'
UNVERIFIED = ('The slot mechanism is native and the status is one a player-side attack already applies, but a '
    'status on an attack that does not use it is not gameplay-proven; allow_unverified_effect is required.')
SLOTS = 4
_CACHE = {}


def policy() -> dict:
    """The reviewed attachment extension (schemas/status_attachment_policy.json), checked against the research:
    semantic ID -> tier. Only statuses no player-side attack applies yet; never a terrain, stim, weather or system
    status (a weather-family status the game itself applies through enemy slots, such as tremor, is allowed)."""
    if 'policy' not in _CACHE:
        research = {item['semanticId']: item for item in json.loads(RESEARCH.read_text(encoding='utf-8'))['statuses']}
        document = json.loads(POLICY.read_text(encoding='utf-8'))
        tiers, never = set(document['tiers']), set(document['neverAttachable'])
        result = {}
        for entry in document['statuses']:
            name, tier = entry['semanticId'], entry['tier']
            status = research.get(name)
            if status is None or tier not in tiers or name in result or name in never:
                raise ValueError(f'status attachment policy: invalid entry {entry!r}')
            if status['attachable']:
                raise ValueError(f'status attachment policy: {name} is already attachable')
            if (tier == 'enemy_slot') != (status['slotUsers'] > 0):
                raise ValueError(f'status attachment policy: {name} tier {tier} contradicts its slot users')
            if tier == 'other_system' and status['family'] in document['neverAttachableFamilies']:
                raise ValueError(f'status attachment policy: {name} is a {status["family"]} status')
            result[name] = tier
        missing = never - set(research)
        if missing:
            raise ValueError(f'status attachment policy: unknown statuses {sorted(missing)}')
        _CACHE['policy'] = {'tiers': result, 'descriptions': document['tiers']}
    return _CACHE['policy']


def load() -> dict:
    if 'catalog' not in _CACHE:
        research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        extended = policy()['tiers']
        _CACHE['catalog'] = {'byType': {item['nativeType']: item for item in research['statuses']},
            'attachable': [item['semanticId'] for item in research['statuses']
                if item['attachable'] or item['semanticId'] in extended],
            'slots': {int(key): value for key, value in research['damageSlots'].items()}}
    return _CACHE['catalog']


def slot_specs(damage_type: int) -> list[dict]:
    """Field specs for one DamageInfo row: suffix, offset, storage, current value and flags."""
    catalog = load()
    slots = catalog['slots'].get(int(damage_type))
    if slots is None:
        return []
    used = [index for index, (kind, _) in enumerate(slots, 1) if kind]
    if used != list(range(1, len(used) + 1)):
        raise ValueError(f'DamageInfo {damage_type} status slots are not packed')
    specs = []
    for slot in used:
        kind = slots[slot - 1][0]
        status = catalog['byType'].get(kind)
        if status is None:
            raise ValueError(f'DamageInfo {damage_type} slot {slot} names unknown status type {kind}')
        specs.append({'suffix': f'status_{slot}_type', 'slot': slot, 'offset': 44 + 8 * (slot - 1), 'storage': 'u32',
            'current': status['semanticId'], 'role': 'type', 'attach': False, 'lastUsed': slot == used[-1]})
    free = len(used) + 1
    if free <= SLOTS:
        specs.append({'suffix': f'status_{free}_type', 'slot': free, 'offset': 44 + 8 * (free - 1), 'storage': 'u32',
            'current': 'none', 'role': 'type', 'attach': True, 'lastUsed': False})
        specs.append({'suffix': f'status_{free}_strength', 'slot': free, 'offset': 48 + 8 * (free - 1),
            'storage': 'f32', 'current': 0.0, 'role': 'strength', 'attach': True, 'lastUsed': False})
    return specs


def projectile_live_evidence() -> dict | None:
    """Live evidence for status references on player / support projectile direct-hit rows (LiberatorFireStatus,
    MaxigunStun); None until that family is live-proven in schemas/live_evidence.json."""
    import live_evidence
    return live_evidence.proven('weapon_projectile_status_reference')


def type_extra(spec: dict, live: dict | None = None) -> dict:
    """Descriptor keys every status slot field carries (added to the generated field). `live` is the live
    evidence of a promoted family: such fields need no acknowledgement."""
    catalog = load()
    allowed = list(catalog['attachable'])
    if spec['role'] == 'type' and spec['current'] not in allowed and spec['current'] != 'none':
        allowed.append(spec['current'])
    extra = {'statusSlot': spec['slot'], 'statusAttach': spec['attach']}
    if live:
        extra['liveEvidence'] = live
    else:
        extra.update(acknowledgement='allow_unverified_effect', acknowledgementReason=UNVERIFIED)
    if spec['role'] == 'type':
        extra['allowedValues'] = allowed
        # 'none' clears a slot only where that keeps the slots packed.
        extra['allowNone'] = spec['attach'] or spec['lastUsed']
    else:
        extra['min'], extra['max'] = 0, 1000
    return extra


def backing_extra(spec: dict) -> dict:
    return {'statusSlot': spec['slot'], 'enum': 'status'} if spec['role'] == 'type' else {'statusSlot': spec['slot']}
