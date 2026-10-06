"""Generate domains/projectile_rows.lua: SpawnProjectile and the hybrid-row member policy for Runtime-owned custom
projectile rows (docs/custom-projectile-rows.md), from research/projectile-rows-F5FEE03DCFDB.json, and the projectile
pool that weapon projectile replacement reads, from research/projectile-pool-F5FEE03DCFDB.json.

Every descriptor offset and every late-lookup member enters the runtime table only when a pinned instruction of the
research uses exactly that offset. The pins are re-proven in game before the first custom spawn of each loaded
game.dll; one mismatch refuses every custom spawn (and nothing else).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/projectile-rows-F5FEE03DCFDB.json'
POOL_RESEARCH = ROOT / 'research/projectile-pool-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/projectile_rows.lua'
CLASSES = {
    'BASE_TYPE': 'the vanilla ProjectileType; must equal the chosen base (every late lookup indexes the vanilla table '
        'with it)',
    'COPIED_AT_SPAWN': 'copied by SpawnProjectile into the spawned projectile; may differ from the base',
    'LATE_LOOKUP': 'read again later through the stored vanilla type; must equal the base',
    'FIRE_PATH_LOOKUP': 'read through the weapon\'s configured type on the fire path, never from a spawned row; must '
        'equal the base',
    'UNKNOWN': 'not proven either way; must equal the base',
}


# Semantic component descriptors. A component owns only labelled COPIED_AT_SPAWN members (checked in build()); composing
# a component copies exactly those members from its donor's live vanilla row. assets: 'donor' = the donor output's
# package must be resident before a spawn (effects, explosions, status visuals); 'none' = plain numbers.
COMPONENTS = [
    {'id': 'visual', 'name': 'ProjectileVisual',
        'members': ['spawn_effect', 'spawn_effect_alternate', 'spawn_effect_parameter', 'spawn_effect_secondary',
            'spawn_effect_record'],
        'assets': 'donor', 'constraints': ['donor_unit_matches_base'],
        'meaning': 'the particle effects created at spawn: the in-flight look (colour is baked into the effect asset)',
        'evidence': 'spawn code: particle effects created with the spawn pose, "start" / "end" variables set to the slot '
            'position; live: the PLAS-1 Scorcher donor visibly changed a Talon-based row (OBSERVED)',
        'live': 'observed'},
    {'id': 'damage', 'name': 'ProjectileDamage', 'members': ['direct_damage'], 'assets': 'donor',
        'catalogueSlot': 'projectile.direct_damage', 'constraints': [],
        'meaning': 'the direct-hit DamageInfo: damage, armour penetration and its status slots',
        'evidence': 'spawn code: copied into the hit record with its armour penetration; live: the RS-422 Railgun donor '
            'dealt clearly more damage on a Talon-based row (consumed VERIFIED, magnitude OBSERVED)',
        'live': 'observed'},
    {'id': 'impact_explosion', 'name': 'ProjectileImpactExplosion', 'members': ['impact_explosion'], 'assets': 'donor',
        'catalogueSlot': 'projectile.impact_explosion', 'constraints': [],
        'meaning': 'the explosion released on impact',
        'evidence': 'spawn code: copied into the hit record, and hit processing reads that copy; live on native rows '
            '(projectile_slot_composition), not yet on a Runtime-owned row',
        'live': 'untested_on_hybrid_rows'},
    {'id': 'ballistics', 'name': 'ProjectileBallistics',
        'members': ['diameter', 'speed', 'mass', 'drag', 'gravity', 'lifetime_variance', 'penetration_slowdown'],
        'assets': 'none', 'constraints': [],
        'meaning': 'flight: diameter, speed, mass, drag, gravity, lifetime variance and penetration slowdown',
        'evidence': 'spawn code: copied into the slot ballistics and hit records (drag constant = 1/2 x 1.2 x pi r^2 x '
            'drag from the diameter); not yet live-tested',
        'live': 'untested'},
]


def components(policy: list[dict]) -> list[dict]:
    """The descriptors with their members resolved against the policy: every member one labelled, whole,
    COPIED_AT_SPAWN entry, owned by one component only."""
    by_label = {}
    for entry in policy:
        if entry.get('label'):
            by_label.setdefault(entry['label'], []).append(entry)
    owned, out = set(), []
    for component in COMPONENTS:
        members = []
        for label in component['members']:
            entries = by_label.get(label, [])
            if len(entries) != 1 or entries[0]['class'] != 'COPIED_AT_SPAWN' or entries[0].get('mask') is not None:
                raise ValueError('component %s: %s is not one whole COPIED_AT_SPAWN member' % (component['id'], label))
            if label in owned:
                raise ValueError('member %s belongs to two components' % label)
            owned.add(label)
            members.append({'label': label, 'offset': entries[0]['offset'], 'width': entries[0]['width']})
        out.append(dict(component, members=members))
    return out


def pool(research: dict) -> dict:
    """The projectile pool as weapon projectile replacement reads it (research/projectile-pool-F5FEE03DCFDB.json):
    the spawn counter and the slot records, every offset a pinned instruction of that research. The pins are
    re-proven in game before the first read of each loaded game.dll."""
    found = json.loads(POOL_RESEARCH.read_text(encoding='utf-8'))
    if found['writes'] or found['protectionChanges']:
        raise ValueError('projectile pool research must be read-only')
    if any(found['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned projectile pool instruction differs between retained snapshots')
    if found['gameDll']['sha256'] != research['gameDll']['sha256']:
        raise ValueError('the projectile pool research covers another game.dll')
    if found['system']['global'] != research['system']['global']:
        raise ValueError('the projectile pool research reads another projectile system')
    layout, proofs = found['pool'], found['proofs']
    asm = [pin['asm'] for rows in proofs.values() for pin in rows]
    def requires(text):
        if not any(text in line for line in asm):
            raise ValueError('projectile pool: %s is not a pinned instruction' % text)
    requires('dword ptr [rcx + 0x%x]' % layout['counter'])
    requires('and r12d, 0x%x' % layout['mask'])
    requires('0x%x]' % (layout['types']['base']))
    requires('0x%x]' % (layout['flags']['base']))
    flight, source, hit = layout['flight'], layout['source'], layout['hit']
    requires('imul r15, rdi, 0x%x' % flight['stride'])
    for member in ('position', 'velocity', 'distance', 'lifetime', 'speed'):
        requires('0x%x]' % (flight['base'] + flight[member]))
    requires('0x%x], eax' % (source['base'] + source['entity']))
    requires('lea rdi, [rsi + 0x%x]' % hit['base'])
    requires('imul rax, rax, 0x%x' % hit['stride'])
    requires('mov dword ptr [rdi + %d], eax' % hit['owner'])
    requires('mov qword ptr [rdi], rax')
    for member in layout['explosions'].values():
        requires('dword ptr [rax + 0x%x]' % member)
    # The impact explosion copy (Gas EAT): stored once at spawn, read on impact, the impact-requested flag.
    requires('mov dword ptr [rdi + 0x%x], ecx' % hit['impactExplosion'])
    requires('[rdi + rcx + 0x%x]' % (hit['base'] + hit['impactExplosion']))
    requires('[rdi + rcx + 0x%x], 1' % (hit['base'] + hit['impactRequested']))
    census = found.get('census') or {}
    if [s['rva'] for s in census.get('stores', [])] != [0x13AA64C]:
        raise ValueError('projectile pool: the impact explosion copy has another store than SpawnProjectile')
    if layout['slots'] != layout['mask'] + 1 or research['system']['active'] != layout['active']:
        raise ValueError('projectile pool slot count or active flag disagrees')
    pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
        for rows in proofs.values() for pin in rows]
    return dict(layout, research=POOL_RESEARCH.name, session=found['session'], semantics=found['semantics'],
        unproven=found['unproven'], pins=sorted(pins, key=lambda pin: pin['rva']))


def pinned(proofs: dict, pattern: str) -> bool:
    return any(re.search(pattern, pin['asm']) for rows in proofs.values() for pin in rows)


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('projectile row research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    natives = (ROOT / 'domains/event_natives.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in natives:
        raise ValueError('projectile row research covers another game.dll than domains/event_natives.lua')
    system, table = research['system'], research['table']
    for key, value in (('system', system['global']), ('settingsTable', table['rva']), ('typeCount', table['typeCount']),
            ('active', system['active'])):
        if not re.search(r'\["projectile"\]=\{[^}]*\["%s"\]=%d[,}]' % (key, value), natives):
            raise ValueError('projectile %s disagrees with domains/event_natives.lua' % key)
    proofs, spawn = research['proofs'], research['spawn']
    descriptor = spawn['descriptor']
    for field in ('position', 'direction', 'row', 'source', 'owner', 'creditor', 'kind'):
        offset = descriptor[field]
        operand = r'\[r14\]' if offset == 0 else r'\[r14 \+ %s\]' % (hex(offset) if offset >= 10 else offset)
        if not pinned(proofs, operand):
            raise ValueError('descriptor %s (+0x%X) is not a pinned read' % (field, offset))
    if descriptor['size'] < descriptor['kind'] + 4 or spawn['template'] != {'kind': 2, 'extra': None}:
        raise ValueError('spawn descriptor template changed')
    if not pinned(proofs, r'^mov dword ptr \[rbp - 0x48\], 2$') or not pinned(proofs, r'^test r13, r13$'):
        raise ValueError('the kind 2 template or the null extra-parameter guard is not pinned')
    if research['row']['size'] != 272:
        raise ValueError('ProjectileInfo size changed')
    policy = research['policy']
    covered = set()
    for entry in policy:
        if entry['class'] not in CLASSES:
            raise ValueError('unknown member class ' + entry['class'])
        if entry['class'] == 'COPIED_AT_SPAWN' and entry.get('mask') is not None:
            raise ValueError('a bitfield bit cannot be copied independently of its word')
        if entry['class'] == 'LATE_LOOKUP':
            if not pinned({'late': proofs['late']}, r'\+ %s\]' % hex(entry['offset'])):
                raise ValueError('late lookup +0x%X is not a pinned read' % entry['offset'])
        if entry['class'] == 'COPIED_AT_SPAWN':
            if not pinned({'copied': proofs['copied']}, r'\+ %s\]' % hex(entry['offset'])):
                raise ValueError('copied member +0x%X is not a pinned spawn-time read' % entry['offset'])
        covered.update(range(entry['offset'], entry['offset'] + entry['width']))
    if covered != set(range(272)):
        raise ValueError('the member policy does not cover every row byte')
    if [e['class'] for e in policy if e['offset'] == 0] != ['BASE_TYPE']:
        raise ValueError('row +0 must be the base type')
    pins = [{'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes'], 'module': 'game'}
        for group in ('spawn', 'copied', 'late', 'fire', 'template', 'visual') for pin in proofs[group]]
    members = []
    for entry in policy:
        item = {'offset': entry['offset'], 'width': entry['width'], 'class': entry['class'], 'reason': entry['reason']}
        for key in ('mask', 'label', 'unit', 'storage', 'type', 'nameLength'):
            if entry.get(key) is not None:
                item[key] = entry[key]
        members.append(item)
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        'spawn': {'rva': spawn['rva'], 'prologue': spawn['prologue'], 'signature': spawn['signature'],
            'descriptor': descriptor, 'kind': spawn['template']['kind'], 'returns': spawn['returns']},
        'system': system, 'table': table,
        'row': {'size': research['row']['size'], 'align': research['row']['align']},
        'classes': CLASSES, 'members': members, 'components': components(policy),
        'unproven': research['unproven'],
        'pins': sorted(pins, key=lambda pin: pin['rva']),
        'pool': pool(research)}


def outputs() -> dict[str, str]:
    return {'domains/projectile_rows.lua': '-- Generated by scripts/generate_projectile_rows.py; do not edit.\nreturn '
        + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale projectile rows: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
