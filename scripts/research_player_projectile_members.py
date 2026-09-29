"""Player-weapon projectile lifetime (+52) and penetration slowdown (+64). Read-only.

The members were proven on support weapons (research_support_weapon_coverage.py: ProjectileInfo +52 / +64, hidden
member-name lengths 9 = life_time and 20 = penetration_slowdown, exact wiki agreement on every stated row). This pass
reads the same members of every ProjectileSettings row a resolved player weapon fires, through the production
resolver against the retained snapshot, and cross-checks them independently against the player weapons' own wiki
values. A branch is publishable when its row is uniquely resolved; the per-weapon wiki check is recorded as evidence.

Output: research/player-projectile-members-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from research_enemy_attacks import resolve_settings  # noqa: E402

OUTPUT = ROOT / 'research/player-projectile-members-F5FEE03DCFDB.json'
CATALOG = ROOT / 'schemas/player_weapon_authoring_catalog.json'
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_player_weapons.json'


def branches(catalog, weapon):
    """(prefix, projectileSettings) of every projectile attack of the weapon's resolved candidate, in the order
    scripts/generate_weapon_authoring.py names them (one: projectile; two: projectile.primary / .alternate)."""
    candidate = catalog['candidates'][weapon['resources'][0]] if weapon['resources'] else {}
    attacks = [a for a in candidate.get('attacks') or [] if a.get('kind') == 'Projectile' and a.get('projectileSettings')]
    return [('projectile' if len(attacks) == 1 else 'projectile.' + ('primary' if i == 0 else 'alternate'),
        a['projectileSettings']) for i, a in enumerate(attacks)]


def build():
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    wiki = {w['name']: w for w in json.loads(WIKI.read_text(encoding='utf-8'))['weapons']}
    types = sorted({b['recordType'] for w in catalog['weapons'] for _, b in branches(catalog, w) if b.get('recordType')})
    rows = {p['type']: p for p in resolve_settings(types, [])['projectiles']}
    weapons, counts = [], Counter()
    for weapon in catalog['weapons']:
        stated = [a['projectile'] for a in (wiki.get(weapon['name']) or {}).get('attacks') or []
            if a.get('kind') == 'Projectile' and a.get('projectile')]
        entry = {'name': weapon['name'], 'branches': []}
        for position, (prefix, backing) in enumerate(branches(catalog, weapon)):
            row = rows.get(backing.get('recordType')) or {}
            settings = row.get('settings') or {}
            same = (settings.get('group'), settings.get('row')) == (backing.get('group'), backing.get('row'))
            values = row.get('values') or {}
            wiki_values = stated[position] if position < len(stated) else {}
            check = {}
            for key, wiki_key in (('penetration_slowdown', 'penetrationSlowdown'), ('lifetime', 'lifetimeSeconds')):
                wiki_value = (wiki_values.get(wiki_key) or {}).get('value')
                if wiki_value is None or key not in values:
                    check[key] = 'wiki_silent'
                else:
                    check[key] = 'exact' if abs(values[key] - wiki_value) < 1e-5 else 'differs'
                counts[key + ':' + check[key]] += 1
            entry['branches'].append({'prefix': prefix, 'recordType': backing.get('recordType'),
                'group': backing.get('group'), 'row': backing.get('row'), 'resolved': same and bool(values),
                'lifetime': values.get('lifetime'), 'penetrationSlowdown': values.get('penetration_slowdown'),
                'wikiCheck': check})
            counts['branches'] += 1
            counts['resolved'] += same and bool(values)
        weapons.append(entry)
    return {'schemaVersion': 1, 'writes': 0, 'fixtureFallback': 'disabled',
        'memberProof': 'ProjectileInfo +52 life_time (name length 9) and +64 penetration_slowdown (name length 20), '
            'exact on every stated support-weapon row (research/support-weapon-coverage-F5FEE03DCFDB.json)',
        'summary': dict(sorted(counts.items())), 'weapons': weapons}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
