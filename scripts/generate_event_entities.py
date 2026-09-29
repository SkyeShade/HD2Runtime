"""Generate the event entity catalog (domains/event_entities.lua) from the pinned datalibrary.

Every entity type that owns a HealthComponentData record, keyed by its type hash (the resource hash of its entity
path, which is also the u64 at the start of a live health descriptor). For each:

- kill: the record's KillScore (+0x30) is greater than 0. This is the game's own rule for counting a death as an
  enemy kill: the kill-credit listener (game.dll 0x129FD00) adds dealt_kills only when the victim's settings KillScore
  is positive (research/event-combat-F5FEE03DCFDB.json). It is what `entity:is_enemy()` and `event.enemy` report.
- faction: from the entity path (content/fac_bugs -> terminids, ...), when the path is known.
- name: the enemy catalog's wiki or class name, else the entity path's leaf, else nil (path hash unknown).
- id: a stable semantic identity. The enemy catalog's semantic id for its 177 classes
  (`enemy/v1/<faction>/<class>`, the same ids hd2.enemy / hd2.structure use); otherwise `entity/v1/<faction or
  content folder>/<path leaf>` for a known path (a leaf shared by two paths gets the type hash appended), else
  `entity/v1/unresolved/<type hash>`. Stable across builds while the resource path is.
- display: the wiki name only where the enemy catalog attaches one (a one-to-one anatomy match); never guessed.
- kind: the enemy catalog's kind (enemy or structure) where it has the class.

A per-instance settings copy (health manager +0x10B0) could differ from the shared record; none is known to change
KillScore, and the snapshots hold none.

It also carries `sources`: the entity types the game keys a player's per-source mission stats by (the kill-credit
listener records each stat under the source entity's type; research/event-mission-F5FEE03DCFDB.json). Guns are
keyed by their weapon entity, stratagems by their payload, throwables by the throwable entity. Each is named from
the reviewed catalogs: player weapons, support weapons, throwables and stratagem payload roots.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from migration import build_view  # noqa: E402
from reference_format import lua  # noqa: E402

OUTPUT = ROOT / 'domains/event_entities.lua'
ENEMIES = ROOT / 'sdk/EnemyAuthoringCapabilities.json'
PLAYER_WEAPONS = ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json'
SUPPORT_WEAPONS = ROOT / 'sdk/SupportWeaponCapabilities.json'
THROWABLES = ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json'
STRATAGEMS = (ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json',
    ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json')
KILL_SCORE = 0x30
FACTIONS = {'fac_bugs': 'terminids', 'fac_cyborgs': 'automatons', 'fac_illuminate': 'illuminate',
    'fac_helldivers': 'helldivers', 'fac_super_earth': 'super_earth'}
AVATAR = 'content/fac_helldivers/cha_avatar/avatar_helldiver'


def paths() -> dict[int, str]:
    sys.path.insert(0, str(ROOT / 'scripts'))
    from hd2_archive import resource_hash
    result = {}
    for line in (build_profile.FILEDIVER / 'hashes/hashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if line and not line.startswith('//'):
            result[resource_hash(line)] = line
    return result


def stat_sources() -> dict:
    """Type hash -> {name, kind} for the stat source types Runtime can name (first catalog wins)."""
    sources = {}

    def add(resource, name, kind):
        key = '%016X' % int(resource, 16)
        if name and key not in sources:
            sources[key] = {'name': name, 'kind': kind}

    for weapon in json.loads(PLAYER_WEAPONS.read_text(encoding='utf-8'))['weapons']:
        for resource in weapon['resources']:
            add(resource, weapon['name'], 'weapon')
    for weapon in json.loads(SUPPORT_WEAPONS.read_text(encoding='utf-8'))['weapons'].values():
        for resource in [weapon.get('canonicalResourceHash')] + list(weapon.get('resourceHashes') or []):
            if resource:
                add(resource, weapon['catalogIdentity'], 'weapon')
    for item in json.loads(THROWABLES.read_text(encoding='utf-8'))['catalog']:
        if item['identity'].get('resource'):
            add(item['identity']['resource'], item['name'], 'throwable')
    # A payload shared by several stratagems (the hellpod) names none of them.
    owners = {}
    for path in STRATAGEMS:
        research = json.loads(path.read_text(encoding='utf-8'))
        for item in list(research['stratagems']) + list(research.get('supportRoots') or []):
            payloads = (item.get('currentRoot') or {}).get('payloads') or []
            for resource in (payloads.values() if isinstance(payloads, dict) else payloads):
                owners.setdefault(resource.upper(), set()).add(item['name'])
    for resource, names in sorted(owners.items()):
        if len(names) == 1:
            add(resource, next(iter(names)), 'stratagem')
    return sources


def build() -> dict:
    view = build_view.from_datalibrary(build_profile.datalibrary(), {})
    if view.build['entitiesSha256'] != build_profile.ENTITY_SHA256:
        raise ValueError('pinned datalibrary changed')
    table = view.component('HealthComponentData')
    known = paths()
    from hd2_archive import resource_hash
    enemy_names, enemy_classes = {}, {}
    for item in json.loads(ENEMIES.read_text(encoding='utf-8'))['classes']:
        enemy_names[resource_hash(item['identity']['path'])] = item['wikiName'] or item['className']
        enemy_classes[resource_hash(item['identity']['path'])] = item
    leaves = {}
    for resource in table.owners:
        path = known.get(resource)
        if path and resource not in enemy_classes:
            leaves.setdefault(path.rsplit('/', 1)[-1], []).append(resource)
    entities = {}
    for resource, (record, _row) in sorted(table.owners.items()):
        path = known.get(resource)
        folder = path.split('/')[1] if path and path.startswith('content/') and path.count('/') > 1 else None
        kill_score = struct.unpack_from('<i', table.records[record], KILL_SCORE)[0]
        entry = {'kill': kill_score > 0}
        name = enemy_names.get(resource) or (path.rsplit('/', 1)[-1] if path else None)
        if name:
            entry['name'] = name
        if FACTIONS.get(folder):
            entry['faction'] = FACTIONS[folder]
        if path == AVATAR:
            entry['avatar'] = True
        enemy = enemy_classes.get(resource)
        if enemy:
            entry['id'] = enemy['semanticId']
            entry['kind'] = enemy['kind']
            if enemy['wikiName']:
                entry['display'] = enemy['wikiName']
        elif path:
            leaf = path.rsplit('/', 1)[-1]
            group = FACTIONS.get(folder) or folder or 'content'
            entry['id'] = f'entity/v1/{group}/{leaf}' + (f'-{resource:016x}' if len(leaves[leaf]) > 1 else '')
        else:
            entry['id'] = f'entity/v1/unresolved/{resource:016X}'
        entities[f'{resource:016X}'] = entry
    if not entities.get(f'{__import__("hd2_archive").resource_hash(AVATAR):016X}', {}).get('avatar'):
        raise ValueError('the Helldiver avatar type is absent from the health owners')
    ids = [entry['id'] for entry in entities.values()]
    if len(ids) != len(set(ids)):
        raise ValueError('semantic entity ids are not unique')
    missing = [item['semanticId'] for key, item in enemy_classes.items() if f'{key:016X}' not in entities]
    if missing:
        raise ValueError('enemy catalog classes without a health type: ' + ', '.join(missing[:5]))
    sources = stat_sources()
    return {'source': {'build': build_profile.BUILD_ID, 'entitiesSha256': build_profile.ENTITY_SHA256,
        'killScoreOffset': KILL_SCORE}, 'entities': entities, 'sources': sources,
        'summary': {'types': len(entities), 'kill': sum(e['kill'] for e in entities.values()),
            'named': sum('name' in e for e in entities.values()), 'sources': len(sources),
            'enemyCatalogIds': sum(e['id'].startswith('enemy/') for e in entities.values()),
            'unresolvedIds': sum(e['id'].startswith('entity/v1/unresolved/') for e in entities.values()),
            'displayNames': sum('display' in e for e in entities.values())}}


def outputs() -> dict[str, str]:
    value = build()
    return {'domains/event_entities.lua': '-- Generated by scripts/generate_event_entities.py; do not edit.\nreturn '
        + lua(value) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale event entity catalog: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
