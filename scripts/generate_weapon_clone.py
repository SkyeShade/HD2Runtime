"""Generate domains/weapon_clone.lua: the carrier weapon clone's reviewed data (research/docs/carrier-weapon-clone-
F5FEE03DCFDB.md) from research/carrier-weapon-clone-F5FEE03DCFDB.json (scripts/research_carrier_weapon_clone.py):

* the component tables as they sit in the entity region (offset, header, index, indices, records, record offset,
  stride, type) and their entity manager slot (the game reads its type records there, in place);
* each clone DONOR (EAT-17) with its reviewed presentation values and its carrier POOL (its expendable component class,
  in order);
* each clone host (EAT-700, EAT-411): its own records (index row, record, owner count 1, an FNV-1a of the native
  bytes) and every member to copy from the donor, with its native and donor bytes and its level (presentation, model,
  full);
* the game.dll pins runtime/weapon_clone.lua re-proves before a write (the type-table readers, the pickup prompt's
  icon path, the Spottable instance manager);
* the EXPENDABLE LIFECYCLE members (research/expendable-carriers-F5FEE03DCFDB.json,
  scripts/research_expendable_carriers.py): every support weapon that discards itself when empty and can never be
  reloaded, in order, each with its clone class, pod capacity, magazine and per-donor clone compatibility (checked here
  to be exactly each donor's pool, in pool order: membership never widens a pool);
* each donor's reviewed ROUNDS (research `roundOverrides`, scripts/research_clone_rounds.py): a round its clone may
  fire instead of its own (the carrier's ProjectileWeapon +0 ProjType := the round's type at every level), with the
  round's chain rows (reviewed bytes, relocated words masked), the code pins of the path that consumes them, its two
  packages (the round's own loadout package and the mission package) and its summary. Checked here: the pins are
  identical in every snapshot, the rows have the strides and masks of their kind, the asset key resolves to the unit
  package in domains/package_residency.lua, and every host of the donor's pool has the full-level ProjType write.

Nothing here is read from a live entity: the donor's values are the pinned research's.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/carrier-weapon-clone-F5FEE03DCFDB.json'
EXPENDABLE = ROOT / 'research/expendable-carriers-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'domains/package_residency.lua'
OUTPUT = 'domains/weapon_clone.lua'
ROW_STRIDES = {'projectile': 272, 'explosion': 152, 'damage': 76, 'template': 40, 'status': 152}
ROW_RELOCATED = {'explosion': [40, 44], 'status': [8, 12]}
PACKAGE_ID = re.compile(r'^0x[0-9A-F]{16}$')


def asset_package(key: str) -> str | None:
    """The package a catalogue dependency key resolves to (domains/package_residency.lua dependencies), or None."""
    m = re.search(r'\[%s\]=\{\["label"\]="[^"]*",\["package"\]="(0x[0-9A-F]{16})"' % re.escape(json.dumps(key)),
        RESIDENCY.read_text(encoding='utf-8'))
    return m.group(1) if m else None


def rounds_of(research: dict, d: dict) -> dict:
    """The reviewed round overrides, validated, in the domain's shape."""
    out = {}
    for donor, rounds in research.get('roundOverrides', {}).items():
        entry = d['donors'].get(donor)
        if not entry:
            raise ValueError(donor + ' has round overrides but is not a clone donor')
        out[donor] = {}
        for name, r in rounds.items():
            where = '%s round %s' % (donor, name)
            if r['hosts'] != entry['pool']:
                raise ValueError(where + ': reviewed for %r, the pool is %r' % (r['hosts'], entry['pool']))
            if any(r['pinnedBytesMismatchPerSnapshot'].values()) or not r['pins']:
                raise ValueError(where + ': a pin differs between retained snapshots')
            kind = r['type']
            if not isinstance(kind, int) or kind <= 0 or kind == entry['projectile']:
                raise ValueError(where + ': not a round of its own: %r' % kind)
            rows = r['rows']
            if not rows or (rows[0]['kind'], rows[0]['id']) != ('projectile', kind):
                raise ValueError(where + ': its chain does not start with its projectile row')
            for row in rows:
                if row['stride'] != ROW_STRIDES.get(row['kind']) or len(row['reviewed']) != 2 * row['stride'] \
                        or any(o not in ROW_RELOCATED.get(row['kind'], []) for o in row['masked']):
                    raise ValueError(where + ': unsupported chain row %s %r' % (row['kind'], row['id']))
            if r['write'] != {'component': 'ProjectileWeaponComponentData', 'offset': 0, 'width': 4,
                    'value': struct.pack('<I', kind).hex(), 'levels': r['write']['levels']}:
                raise ValueError(where + ': its write is not the ProjType member: %r' % r['write'])
            for carrier in entry['pool']:
                c = d['carriers'][carrier]
                proj = [w for w in c['writes']
                    if w['component'] == 'ProjectileWeaponComponentData' and w['offset'] == 0]
                if len(proj) != 1 or proj[0]['width'] != 4 or proj[0]['level'] != 'full' \
                        or proj[0]['donor'] != struct.pack('<I', entry['projectile']).hex() \
                        or proj[0]['native'] == r['write']['value']:
                    raise ValueError(where + ': %s has no reviewed full-level ProjType write' % carrier)
            packages = r['packages']
            for role in ('unit', 'mission'):
                if not PACKAGE_ID.match(packages[role]['id']) or packages[role]['inBundleDatabase'] is not True:
                    raise ValueError(where + ': its %s package is not a package of this build' % role)
            if asset_package(r['assetKey']) != packages['unit']['id']:
                raise ValueError(where + ': its asset key %r does not resolve to its unit package %s' % (
                    r['assetKey'], packages['unit']['id']))
            sem = r['semantics']
            sub = sem.get('submunition')
            out[donor][name] = {'name': name, 'type': kind, 'weapon': r['weaponSide']['weapon'],
                'assetKey': r['assetKey'],
                'packages': {role: {'id': packages[role]['id'], 'name': packages[role]['name']}
                    for role in ('unit', 'mission')},
                'impact': sem['round']['impact'], 'expiry': sem['round']['expiry'],
                'proximity': sem['round']['proximity'], 'arming': sem['round']['arming'],
                'lifetime': sem['round']['lifetime'], 'speed': sem['round']['speed'],
                'direct': {'standard': sem['round']['damage']['standard'],
                    'armorPenetration': sem['round']['damage']['armorPenetration'][0]},
                'submunition': {'count': sem['explosion']['shrapnel']['count'], 'projectile': sub['type'],
                    'explosion': sub['impact']} if sub else None,
                'summary': r['summary'],
                'rows': [{'kind': row['kind'], 'id': row['id'], 'table': int(row['table'], 16), 'stride': row['stride'],
                    'reviewed': row['reviewed'], 'masked': row['masked']} for row in rows],
                'pins': [{'rva': p['rva'], 'hex': p['hex'], 'label': p['label']} for p in r['pins']]}
    return out


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('the carrier weapon clone research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    d = research['domain']
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    for name, c in d['components'].items():
        known = '["%s"]={["offset"]=%d,' % (name, c['offset'])
        if ('["%s"]=' % name) in profile and known not in profile:
            raise ValueError(name + ': the research table offset differs from schemas/current.lua')
    for carrier in d['carriers'].values():
        if any(r['ownerCount'] != 1 for r in carrier['records'].values()):
            raise ValueError('a clone host record is shared')
        for w in carrier['writes']:
            if w['width'] not in (1, 4, 8, 12) or w['level'] not in ('model', 'full'):
                raise ValueError('unsupported clone write: %r' % w)
    expendable = json.loads(EXPENDABLE.read_text(encoding='utf-8'))
    if expendable['writes'] or expendable['protectionChanges']:
        raise ValueError('the expendable carriers research must be read-only')
    if any(expendable['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('an expendable carriers pin differs between retained snapshots')
    ex = expendable['domain']
    for donor, entry in d['donors'].items():
        if donor not in ex['members']:
            raise ValueError(donor + ' is a clone donor but not an expendable lifecycle member')
        compatible = [n for n in ex['order'] if ex['members'][n]['clone'].get(donor, {}).get('compatible') is True]
        if compatible != entry['pool']:
            raise ValueError('%s: clone-compatible members %r differ from its pool %r' % (donor, compatible,
                entry['pool']))
    return {'source': {'research': RESEARCH.name, 'expendables': EXPENDABLE.name, 'build': d['build']},
        'entityManager': d['entityManager'], 'slotBase': d['slotBase'],
        'spottableInstances': d['spottableInstances'],
        'levels': d['levels'],
        'components': d['components'], 'donors': d['donors'], 'carriers': d['carriers'],
        'expendables': ex,
        'pins': [{'rva': p['rva'], 'hex': p['hex'], 'label': p['label']} for p in d['pins']],
        'rounds': rounds_of(research, d)}


def outputs() -> dict[str, str]:
    return {OUTPUT: '-- Generated by scripts/generate_weapon_clone.py; do not edit.\nreturn ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale generated weapon clone domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
