"""Generate domains/player_equipment.lua: the inventory, deposit, magazine, avatar action context and ability layouts,
the Supply Pack's self-use ability and the two game functions runtime/player_equipment.lua calls, with every pinned
instruction it re-proves first, from research/player-equipment-F5FEE03DCFDB.json
(research/docs/player-equipment-F5FEE03DCFDB.md), plus the item catalog (entity type -> the name mods already use).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/player-equipment-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/player_equipment.lua'


def mask(text: str) -> dict:
    value = int(text, 16)
    return {'hi': value >> 32, 'lo': value & 0xFFFFFFFF}


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges'] or research['nativeCalls']:
        raise ValueError('player equipment research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    if not research['purity']['needsAmmo']['pure']:
        raise ValueError('needs_ammo is not a pure query')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the player equipment research covers another build than schemas/current.lua')
    pins = [{'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role'] or pin['asm']}
        for rows in research['proofs'].values() for pin in rows]
    pins += [{'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']}
        for pin in research['dataPins']]
    pins.sort(key=lambda pin: pin['rva'])
    avatar = dict(research['avatar'])
    avatar['mayActMask'] = mask(avatar.pop('mayActMaskHigh'))
    avatar['blockingMask'] = mask(avatar.pop('mayActMaskLow'))
    items = {}
    for key, item in sorted(research['catalog'].items()):
        entry = {'name': item['name'], 'kind': item['kind']}
        if item.get('api'):
            entry['api'] = item['api']
        if item.get('magazine'):
            entry['magazine'] = item['magazine']
        for extra in ('feeds', 'carries'):
            if item.get(extra):
                entry[extra] = item[extra]
        fact = research['tableFacts'].get(key)
        if fact and 'equipmentType' in fact:
            entry['equipmentType'] = fact['equipmentType']
        if fact and fact.get('deposit'):
            entry['deposit'] = {k: fact['deposit'][k] for k in ('capacity', 'startAmount', 'refillAmount',
                'otherAbility', 'selfAbility')}
        items[key] = entry
    natives = {name: {'rva': value['rva'], 'prologue': value['prologue']} for name, value in research['natives'].items()}
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        # [game + global] = the inventory manager. The avatar's record index through the hash at + hash ({buckets,
        # capacity, empty, multiplier}); descriptors at + descriptors (8 per record); the record at + records + index *
        # stride: slots (entity ids, 0 = empty), selection (u32), throwable (u64 resource); counts at + counts + index *
        # countStride (+ throwableCount: u32).
        'inventory': research['inventory'],
        # [game + global] = the deposit manager: hash, descriptors, live state (+ amount u32, + drone network id u32);
        # the definition: per-instance override (overrideHash -> overrideRecords + i * definitionStride), else
        # [[game + settings.entityManager] + settings.table]: buckets entries of entryStride {u64 type, u32 index},
        # type % buckets with linear probing; definition at table + records + index * definitionStride.
        'deposit': research['deposit'],
        # [game + global] = the weapon magazine manager: record + spare (spare magazines), + rounds (in the magazine).
        'magazine': research['magazine'],
        # [game + global] = the avatar manager: the action context at global value + context + index * stride (fields:
        # entity, ability, target, extra); flags at + flags + index * stride (two u64: busy is bit busyBit of the
        # second; may act when (second & mayActMask) == 0, (first & blockingMask) == 0 and first has mayActRequired).
        'avatar': avatar,
        # [game + global] = the ability manager: record + id (running ability), + active (byte).
        'ability': research['ability'],
        'supplyPack': research['supplyPack'],
        # try_start_action(context, request {ability, target, extra}) -> bool, and needs_ammo(_, user) -> bool (a pure
        # query: its whole call tree writes nothing).
        'natives': natives,
        'items': items,
        'pins': pins}


def outputs() -> dict[str, str]:
    return {'domains/player_equipment.lua': '-- Generated by scripts/generate_player_equipment.py; do not edit.\n'
        'return ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale player equipment domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
