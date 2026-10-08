"""The real roots of the seven player weapons the stat-fingerprint mapper resolves to two roots (DUPLICATE).

Each weapon's catalogue entry lists two candidate roots that tie on every compared stat; the first was picked by hash
order. This research proves which root is the weapon a player carries, from three kinds of evidence:
  * equipped_snapshot: a retained snapshot with the weapon equipped; the player's inventory slot holds an entity of
    exactly this root (research_player_equipment.observe). LAS-5 Scythe, LAS-7 Dagger (2026-10-08 T162919Z),
    SMG-37 Defender, CQC-73 Entrenchment Tool (T163453Z);
  * underbarrel: the other root is a host weapon's underbarrel (research/underbarrel-weapons catalogCorrections).
    GP-31 Grenade Pistol, P-72 Crisper;
  * call_in_rack: the other root is the one a support weapon's call-in rack attaches (research/support-weapon-coverage
    deliveredRoot), and the kept root's resource path names the weapon. CQC-42 Machete.

Writes research/weapon-roots-F5FEE03DCFDB.json; scripts/generate_weapon_authoring.py applies it to the catalogue
(resources = [the proven root], resolution UNIQUE). Read-only on the snapshots.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'research/weapon-roots-F5FEE03DCFDB.json'
UNDERBARREL = ROOT / 'research/underbarrel-weapons-F5FEE03DCFDB.json'
SUPPORT_COVERAGE = ROOT / 'research/support-weapon-coverage-F5FEE03DCFDB.json'
CATALOG = ROOT / 'schemas/player_weapon_authoring_catalog.json'

# Snapshot -> {slot: weapon}: what the user equipped for the capture.
SNAPSHOTS = {
    'F5FEE03DCFDB-20261008T162919Z-weapon-roots-scythe-dagger.hd2snap':
        {'primary': 'LAS-5 Scythe', 'secondary': 'LAS-7 Dagger'},
    'F5FEE03DCFDB-20261008T163453Z-weapon-roots-defender-etool.hd2snap':
        {'primary': 'SMG-37 Defender', 'secondary': 'CQC-73 Entrenchment Tool'},
}
# What each dropped root is (the reviewed identification, for the record).
DROPPED_IS = {
    'LAS-5 Scythe': 'laser_rifle_charge: another beam entity (its heat matches no published Scythe value)',
    'LAS-7 Dagger': 'a non-loadout beam entity (its 2000 heat is the source of the old 2000-vs-100 disagreement)',
    'SMG-37 Defender': 'the SEAF SMG (seaf_smg package, foley_seafs banks)',
    'CQC-73 Entrenchment Tool': 'the world/support shovel (survival_shovel, the CQC-72 support weapon)',
}


def equipped():
    import research_player_equipment as equipment
    items = equipment.catalog()
    out = []
    for snapshot, slots in SNAPSHOTS.items():
        observation = equipment.observe(snapshot, items)
        player = observation['players'][0]
        for slot, weapon in slots.items():
            seen = player['slots'][slot]
            if seen['name'] != weapon:
                raise ValueError('%s: the %s slot holds %r, not %s' % (snapshot, slot, seen['name'], weapon))
            out.append({'weapon': weapon, 'provenRoot': '0x' + seen['type'],
                'evidence': {'kind': 'equipped_snapshot', 'snapshot': snapshot, 'slot': slot,
                    'entity': seen['entity'], 'entityType': '0x' + seen['type']}})
    return out


def underbarrel():
    data = json.loads(UNDERBARREL.read_text(encoding='utf-8'))
    out = []
    for item in data['catalogCorrections']:
        (kept,) = item['keptRoots']
        out.append({'weapon': item['weapon'], 'provenRoot': kept, 'droppedRoots': [item['dropRoot']],
            'droppedIs': 'the %s underbarrel' % ', '.join(item['underbarrelOf']),
            'evidence': {'kind': 'underbarrel', 'source': UNDERBARREL.name, 'underbarrelOf': item['underbarrelOf']}})
    return out


def machete():
    data = json.loads(SUPPORT_COVERAGE.read_text(encoding='utf-8'))
    found = []

    def walk(value, name):
        if isinstance(value, dict):
            paths = (value.get('structuralConfirmation') or {}).get('paths') or {}
            if '0x792D5D2A340FD6E6' in paths and value.get('deliveredRoot') == '0x5F3EC9BDA2BD8553':
                found.append((name, paths))
            for key, item in value.items():
                walk(item, key)
        elif isinstance(value, list):
            for item in value:
                walk(item, name)
    walk(data, None)
    hammer = found[0][1] if len(found) == 1 and found[0][0] == 'CQC-20 Breaching Hammer' else None
    if not hammer or not hammer['0x792D5D2A340FD6E6'].endswith('/machete/machete') \
            or not hammer['0x5F3EC9BDA2BD8553'].endswith('/sledge_hammer/sledge_hammer'):
        raise ValueError('the CQC-20 Breaching Hammer call-in rack evidence changed')
    return [{'weapon': 'CQC-42 Machete', 'provenRoot': '0x792D5D2A340FD6E6', 'droppedRoots': ['0x5F3EC9BDA2BD8553'],
        'droppedIs': 'the CQC-20 Breaching Hammer (sledge_hammer), the root its call-in rack attaches',
        'evidence': {'kind': 'call_in_rack', 'source': SUPPORT_COVERAGE.name, 'paths': hammer}}]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.parse_args()
    catalog = {w['name']: w for w in json.loads(CATALOG.read_text(encoding='utf-8'))['weapons']}
    rows = underbarrel() + equipped() + machete()
    for row in rows:
        entry = catalog[row['weapon']]
        roots = entry.get('candidateRoots') or entry['resources']
        if row['provenRoot'] not in roots or len(roots) != 2:
            raise ValueError('%s: %s is not one of its two candidate roots %r' % (row['weapon'], row['provenRoot'],
                roots))
        row.setdefault('droppedRoots', [r for r in roots if r != row['provenRoot']])
        if 'droppedIs' not in row:
            row['droppedIs'] = DROPPED_IS[row['weapon']]
    rows.sort(key=lambda r: r['weapon'])
    value = {'schemaVersion': 1, 'gameFingerprint': 'F5FEE03DCFDB',
        'scope': 'The real root of each player weapon the stat-fingerprint mapper resolves to two roots (DUPLICATE). '
            'Applied by scripts/generate_weapon_authoring.py: resources = [provenRoot], resolution UNIQUE.',
        'corrections': rows}
    OUTPUT.write_text(json.dumps(value, indent=2) + '\n', newline='\n')
    print('wrote %s (%d weapons)' % (OUTPUT.relative_to(ROOT), len(rows)))


if __name__ == '__main__':
    main()
