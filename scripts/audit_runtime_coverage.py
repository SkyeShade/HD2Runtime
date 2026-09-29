"""Wiki-vs-Runtime coverage audit for build F5FEE03DCFDB. Read-only; nothing here touches the game.

For every family the scraped wiki datasets describe (stratagems, support and player weapons, throwables, boosters,
vehicles, enemies and structures, status effects) this compares what the wiki states with what the generated Runtime
catalogs expose, stat by stat, through a reviewed map from each wiki stat to the Runtime semantic fields that author
it. The wiki is the semantic guide only: a stat counts as covered when the Runtime publishes a writable field for
it, whatever the wiki's number is.

Output: research/runtime-coverage-audit-F5FEE03DCFDB.json and docs/research/runtime-coverage-audit-F5FEE03DCFDB.md.

  py scripts/audit_runtime_coverage.py [--check]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT.parent / 'HD2WikiImporter/output'
SDK = ROOT / 'sdk'
JSON_OUTPUT = ROOT / 'research/runtime-coverage-audit-F5FEE03DCFDB.json'
MD_OUTPUT = ROOT / 'docs/research/runtime-coverage-audit-F5FEE03DCFDB.md'

# Wiki stratagem stat -> Runtime semantic fields that author it (any one writable counts).
STRATAGEM_STATS = {
    'cooldownSeconds': ('stratagem.cooldown',),
    'uses': ('stratagem.max_uses', 'eagle.uses_per_rearm'),   # Eagle pages state uses per rearm
    'rearmTimeSeconds': ('eagle.rearm_time',),
    'charges': ('eagle.uses_per_rearm',),
    'durationSeconds': ('orbital.duration',),
    'salvos': ('minefield.salvos',),
    'capacity': ('minefield.mines_per_salvo', 'weapon.capacity', 'magazine.capacity', 'rounds.capacity',
        'deposit.capacity'),
    'targetingRadiusMeters': ('orbital.search_radius',),
    'callInTimeSeconds': (),
    'volleys': (), 'strikes': (), 'bombsPerSalvo': (), 'projectilesPerStrike': (),
    'delayBetweenSalvosSeconds': (), 'delayBetweenShotsSeconds': (),
    'trackingSpeedMetersPerSecond': ('orbital.movement_speed',),
}
STRATAGEM_STAT_NOTES = {
    'callInTimeSeconds': 'The resolved spawn-time scalar does not reproduce the call-in time across families.',
    'volleys': 'Barrage delivery arrays are preserved as structure; no scalar volley count is invented.',
    'strikes': 'Barrage delivery arrays are preserved as structure.',
    'bombsPerSalvo': 'Barrage delivery arrays are preserved as structure.',
    'projectilesPerStrike': 'Barrage delivery arrays are preserved as structure.',
    'delayBetweenSalvosSeconds': 'Barrage timing lives in the delivery arrays; not a proven scalar.',
    'delayBetweenShotsSeconds': 'Barrage timing lives in the delivery arrays; not a proven scalar.',
    'trackingSpeedMetersPerSecond': 'The orbital laser movement speed (10 m/s, equal to the wiki).',
    'targetingRadiusMeters': 'Only the orbital laser search radius is proven.',
    'salvos': 'Proven for the four minefields only; barrage salvos have no scalar owner.',
    'durationSeconds': 'Proven for the orbital laser only.',
}
# Wiki weapon stat -> Runtime fields (normalized: domain + last path component).
WEAPON_STATS = {
    'recoil': ('weapon.recoil', 'weapon.recoil_climb_vertical', 'weapon.recoil_climb_horizontal'),
    'horizontalRecoil': ('weapon.horizontal_recoil', 'weapon.recoil_drift_horizontal', 'weapon.recoil_climb_horizontal'),
    'verticalRecoil': ('weapon.vertical_recoil', 'weapon.recoil_drift_vertical', 'weapon.recoil_climb_vertical'),
    'spread': ('weapon.horizontal_spread', 'weapon.vertical_spread'),
    'sway': ('weapon.sway',),
    'ergonomics': ('weapon.ergonomics',),
    'fireRateRpm': ('weapon.fire_rate',),
    # Heat weapons state their heatsinks as magazines; backpack-fed weapons carry ammunition in the backpack deposit.
    'capacity': ('weapon.capacity', 'magazine.capacity', 'rounds.capacity', 'rounds.feed_capacity_1', 'heat.capacity',
        'deposit.capacity'),
    'spareMagazines': ('magazine.spare_magazines', 'rounds.spare_rounds', 'heatsink.spare'),
    'startingMagazines': ('magazine.starting_magazines', 'rounds.starting_rounds', 'heatsink.starting',
        'deposit.start_amount'),
    'magsFromSupply': ('magazine.magazines_from_supply', 'rounds.rounds_from_supply', 'heatsink.from_supply',
        'deposit.refill_amount'),
    # The game derives the ammo-box refill from the supply refill (max(1, floor(supply / 2))), so the stat is authored
    # through magazines_from_supply / rounds_from_supply; the ammo-box field itself is published read-only.
    'magsFromAmmoBox': ('magazine.magazines_from_supply', 'rounds.rounds_from_supply', 'heatsink.from_ammo_box',
        'deposit.refill_amount'),
}
WEAPON_STAT_NOTES = {'magsFromAmmoBox': 'Derived by the game from the supply refill; authored through it.',
    'capacity': 'Effective magazine capacity owned by a default customization option stays read-only.',
    'fireRateRpm': 'Charge-controlled weapons (Railgun, Epoch, Arc Thrower, Meltagun) and selector sentinels are '
        'not exposed as ordinary RPM.',
    'projectile.dragFactor': 'Guided launchers (Spear, Commando, W.A.S.P.): the native row matches the wiki on '
        'damage, velocity and mass but not drag / gravity, so the branch stays PARTIAL.'}
ATTACK_STATS = {
    'damage.standard': ('damage.standard_damage', 'explosion.standard_damage'),
    'damage.durable': ('damage.durable_damage', 'explosion.durable_damage'),
    'projectile.initialVelocityMetersPerSecond': ('projectile.velocity',),
    'projectile.massGrams': ('projectile.mass',),
    'projectile.dragFactor': ('projectile.drag',),
    'projectile.gravityFactor': ('projectile.gravity',),
    'projectile.penetrationSlowdown': ('projectile.penetration_slowdown',),
    'projectile.pelletCount': ('projectile.pellet_count',),
}
FAMILY_DOMAINS = ('projectile', 'explosion', 'damage', 'statusSlot', 'status', 'beam', 'arc', 'spray', 'terminal')


def family(field_id):
    """Output family of a field: DamageInfo status slots (damage.status_<k>_*) are counted apart from the other
    DamageInfo members; status.* are status definitions."""
    return 'statusSlot' if re.search(r'\.status_\d_(type|strength)$', field_id) else field_id.split('.')[0]

# Native-only discoveries: members found in the native data with a plausible role but no independent proof, ranked by
# expected value. None is exposed writable; each needs the listed proof first.
CANDIDATES = [
    {'rank': 1, 'member': 'DamageInfo status slots on enemy attacks',
     'where': 'rows already reached by the proven enemy mount chains (DamageInfo, projectile and explosion rows are '
        'published)',
     'evidence': 'Same slot layout as player weapons; the status catalog applies unchanged',
     'missing': 'Packaging only: the enemy domain does not yet accept status references', 'risk': 'low'},
    {'rank': 2, 'member': 'Minefield floats +8 / +12 / +16 / +28 (arming, trigger, spacing candidates)',
     'where': 'MinefieldComponent of the four mine deployers (0.001 / 0.2 / 0.25 / 0; AT 1.0 / 0.2 / 0.2 / 0)',
     'evidence': 'Typed f32 members with hidden name lengths 12 / 19 / 8 / 19; AT differs as its slower arming would',
     'missing': 'Any stated arming or trigger value (the wiki states none) or a live A/B test',
     'risk': 'medium'},
    {'rank': 3, 'member': 'Thrower slot floats +240..+280 (throw distance band 5-15 / 7-17 / 7-15.5 m, angles)',
     'where': 'ThrowerComponent slot 0 of the mine deployers and the caltrops grenade',
     'evidence': 'Typed f32 members; the min/max pairs differ per mine as spread would',
     'missing': 'The wiki only says "10-20 meters"; needs a live measurement',
     'risk': 'medium'},
    {'rank': 4, 'member': 'TurretComponent +16 / +36 / +40',
     'where': 'Every turreted sentry and enemy turret',
     'evidence': 'Typed members beside the proven turn speeds and limits',
     'missing': 'No published table value; needs a live test',
     'risk': 'medium'},
    {'rank': 5, 'member': 'SensorEye field-of-view members and targeting/retarget timers',
     'where': 'SensorEyeComponent (after +0 range) and the sentry targeting components',
     'evidence': 'Typed members; retarget/search delays are plausible from layout only',
     'missing': 'No wiki statement; timers need a live observation',
     'risk': 'medium'},
    {'rank': 6, 'member': 'HellpodPayload +0',
     'where': 'Every deployable payload',
     'evidence': 'Beside the gameplay-proven lifetime (+4)',
     'missing': 'Meaning unknown; no stated value correlates',
     'risk': 'high'},
    {'rank': 7, 'member': 'Enemy melee / ability attacks (Charger ram, Stalker tongue, Bile Titan vomit, Hulk flamer)',
     'where': 'Not reached by any mount chain; melee/ability systems',
     'evidence': 'The wiki lists damage for 71 ranged and many melee attacks; rows with equal values exist',
     'missing': 'A structural owner linking the class to the row (a value match alone is not identity)',
     'risk': 'high'},
    {'rank': 8, 'member': 'Enemy movement speed, detection and aggression members',
     'where': 'Enemy AI / locomotion components',
     'evidence': 'None independent', 'missing': 'Everything; deliberately not attempted (speculative AI fields)',
     'risk': 'high'},
    {'rank': 9, 'member': 'Stratagem call-in time', 'where': 'StratagemDefinition spawn-time scalar',
     'evidence': 'A spawn-time member exists', 'missing': 'It does not reproduce the wiki call-in time across families',
     'risk': 'high'},
]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def items(document, key):
    return document[key] if isinstance(document, dict) else document


def normal(field_id):
    parts = field_id.split('.')
    return parts[0] + '.' + parts[-1] if len(parts) > 2 else field_id


def stated(value):
    return value not in (None, [], {}, '')


def stratagem_audit():
    catalog = load(SDK / 'StratagemAuthoringCapabilities.json')
    by_name = {s['name']: s for s in catalog['stratagems']}
    writable = defaultdict(set)
    for field in catalog['fieldInstances']:
        if field.get('editable'):
            writable[field['target']['stratagem']].add(normal(field['semanticFieldId']))
    # Vehicles and backpacks are authored in their own catalogs; count those fields for their stratagems too.
    for field in load(SDK / 'VehicleWeaponCapabilities.json')['fieldInstances']:
        if field.get('writable'):
            writable[field['target']['weapon'].split(' / ')[0]].add(normal(field['semanticFieldId']))
    for source, key in (('VehicleAuthoringCapabilities.json', 'vehicle'), ('BackpackAuthoringCapabilities.json', 'backpack')):
        for field in load(SDK / source)['fieldInstances']:
            if field.get('editable'):
                writable[field['target'][key]].add(normal(field['semanticFieldId']))
    wiki, seen = [], set()
    for source, category in (('wiki_offensive_stratagems', 'offensive'), ('wiki_non_offensive_stratagems', None),
            ('wiki_vehicle_stratagems', 'vehicle')):
        for item in items(load(WIKI / (source + '.json')), 'stratagems'):
            if item['name'] in seen:        # vehicles appear in both the non-offensive and vehicle datasets
                continue
            seen.add(item['name'])
            wiki.append((item, category or (item.get('normalizedFamily') or item.get('family') or '').lower()))
    rows, stat_totals = [], defaultdict(Counter)
    for item, family in wiki:
        name = item['name']
        runtime = by_name.get(name)
        fields = writable.get(name, set())
        stats = dict(item.get('stratagem') or {})
        stats.update({k: v for k, v in (stats.pop('extraNormalizedFields', None) or {}).items()})
        stat_rows = {}
        for stat, targets in STRATAGEM_STATS.items():
            if not stated(stats.get(stat)) or stats.get(stat) == 'Unlimited' and stat == 'uses' and not runtime:
                continue
            covered = bool(set(targets) & fields)
            stat_rows[stat] = covered
            stat_totals[stat]['stated'] += 1
            stat_totals[stat]['covered'] += covered
        domains = sorted({field.split('.')[0] for field in fields})
        attacks = [a for a in (item.get('attacks') or [])]
        rows.append({'name': name, 'family': family, 'resolved': bool(runtime),
            'rootResolution': runtime and runtime['rootResolution'], 'writableFields': len(fields),
            'writableDomains': domains, 'stats': stat_rows,
            'uncoveredStats': sorted(k for k, v in stat_rows.items() if not v),
            'attackBranchesWritable': sorted(d for d in domains if d in FAMILY_DOMAINS),
            'wikiAttacks': len(attacks)})
    runtime_only = sorted(set(by_name) - {row['name'] for row in rows})
    return {'wikiStratagems': len(rows), 'resolved': sum(r['resolved'] for r in rows),
        'withWritableFields': sum(1 for r in rows if r['writableFields']),
        'statCoverage': {stat: dict(counts, note=STRATAGEM_STAT_NOTES.get(stat)) for stat, counts in
            sorted(stat_totals.items())},
        'runtimeOnly': runtime_only, 'stratagems': rows}


def weapon_audit(wiki_file, catalog_rows):
    wiki = items(load(WIKI / wiki_file), 'weapons')
    rows, stat_totals = [], defaultdict(Counter)
    for weapon in wiki:
        name = weapon['name']
        fields = catalog_rows.get(name)
        stats = weapon.get('weaponStats') or (weapon.get('normalizedFields') or {}).get('weaponStats') or {}
        stat_rows = {}
        for stat, targets in WEAPON_STATS.items():
            if not stated(stats.get(stat)):
                continue
            covered = bool(fields and set(targets) & fields)
            stat_rows[stat] = covered
            stat_totals[stat]['stated'] += 1
            stat_totals[stat]['covered'] += covered
        for attack in weapon.get('attacks') or []:
            for stat, targets in ATTACK_STATS.items():
                group, key = stat.split('.')
                if not stated((attack.get(group) or {}).get(key)):
                    continue
                covered = bool(fields and set(targets) & fields)
                stat_rows.setdefault(stat, False)
                stat_rows[stat] = stat_rows[stat] or covered
        for stat in [s for s in stat_rows if s in ATTACK_STATS]:
            stat_totals[stat]['stated'] += 1
            stat_totals[stat]['covered'] += stat_rows[stat]
        rows.append({'name': name, 'resolved': fields is not None, 'writableFields': len(fields or ()),
            'writableDomains': sorted({f.split('.')[0] for f in fields or ()}),
            'uncoveredStats': sorted(k for k, v in stat_rows.items() if not v)})
    return {'wikiWeapons': len(rows), 'resolved': sum(r['resolved'] for r in rows),
        'withWritableFields': sum(1 for r in rows if r['writableFields']),
        'statCoverage': {stat: dict(counts, note=WEAPON_STAT_NOTES.get(stat)) for stat, counts in
            sorted(stat_totals.items())}, 'weapons': rows}


def support_rows():
    catalog = load(SDK / 'SupportWeaponAuthoringCapabilities.json')
    rows = {weapon['name']: set() for weapon in catalog['weapons']}
    for field in catalog['fieldInstances']:
        if field.get('writable'):
            rows.setdefault(field['supportWeapon'], set()).add(normal(field['semanticFieldId']))
    # Backpack-fed weapons: their ammunition is the backpack deposit (hd2.support_weapon(name):backpack()).
    backpacks = defaultdict(set)
    for field in load(SDK / 'BackpackAuthoringCapabilities.json')['fieldInstances']:
        if field.get('editable'):
            backpacks[field['target']['backpack']].add(normal(field['semanticFieldId']))
    for weapon in catalog['weapons']:
        if weapon.get('ammoBackpack'):
            rows[weapon['name']] |= backpacks[weapon['ammoBackpack']['backpack']]
    return rows


def player_rows():
    catalog = load(SDK / 'PlayerWeaponAuthoringCapabilities.json')
    return {weapon['name']: {normal(f['semanticFieldId']) for f in weapon['fields'] if f.get('editable')}
        for weapon in catalog['weapons']}


def family_audit():
    """Writable output-family fields per catalog (projectile / explosion / damage / status / beam / arc / spray)."""
    result = {}
    sources = {'player_weapons': [(f['semanticFieldId'], f.get('editable')) for w in
            load(SDK / 'PlayerWeaponAuthoringCapabilities.json')['weapons'] for f in w['fields']],
        'support_weapons': [(f['semanticFieldId'], f.get('writable')) for f in
            load(SDK / 'SupportWeaponAuthoringCapabilities.json')['fieldInstances']],
        'stratagems': [(f['semanticFieldId'], f.get('editable')) for f in
            load(SDK / 'StratagemAuthoringCapabilities.json')['fieldInstances']],
        'vehicle_weapons': [(f['semanticFieldId'], f.get('writable')) for f in
            load(SDK / 'VehicleWeaponCapabilities.json')['fieldInstances']],
        'enemies': [(f['semanticFieldId'], f.get('editable')) for f in
            load(SDK / 'EnemyAuthoringCapabilities.json')['fieldInstances']]}
    throwables = load(SDK / 'ThrowableAuthoringCapabilities.json')['summary']['writableByTarget']
    for name, fields in sources.items():
        counts = Counter(family(field) for field, writable in fields if writable)
        result[name] = {domain: counts.get(domain, 0) for domain in FAMILY_DOMAINS}
    result['throwables'] = {'explosion': throwables.get('explosion', 0) + throwables.get('bomblet_explosion', 0),
        'damage': throwables.get('damage', 0), 'status': throwables.get('status_effect', 0),
        'projectile': throwables.get('shrapnel', 0) + throwables.get('bomblets', 0)}
    player = load(SDK / 'PlayerWeaponAuthoringCapabilities.json')['summary']['familyCoverage']
    vehicle = load(SDK / 'VehicleAuthoringCapabilities.json')['summary']['mountedWeaponsByFamily']
    gaps = [
        {'family': 'beam', 'detail': f"player beam weapons: {player['beam']['weaponsWithProjectileOrDamageWrites']} of "
            f"{player['beam']['weapons']} with damage writes; {vehicle['beam']} beam mounted weapons discovered"},
        {'family': 'spray', 'detail': f"player spray/flame weapons: {player['spray_flame']['weaponsWithProjectileOrDamageWrites']} of "
            f"{player['spray_flame']['weapons']}; enemy sprays with no DamageInfo of their own are not published"},
        {'family': 'melee', 'detail': f"player melee: {player['melee']['weaponsWithProjectileOrDamageWrites']} of "
            f"{player['melee']['weapons']}; enemy melee attacks have no structural owner"},
        {'family': 'arc', 'detail': f"player arc weapons: {player['arc']['weaponsWithProjectileOrDamageWrites']} of "
            f"{player['arc']['weapons']}; {vehicle['arc']} arc mounted weapons discovered"},
        {'family': 'status', 'detail': 'status references on player, support and mounted weapons; not yet on '
            'stratagem, throwable, booster or enemy attacks'},
    ]
    return {'writableFieldsByCatalog': result, 'gaps': gaps}


def enemy_audit():
    catalog = load(SDK / 'EnemyAuthoringCapabilities.json')
    research = load(ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json')['summary']
    wiki = items(load(WIKI / 'wiki_enemies.json'), 'enemies')
    structures = items(load(WIKI / 'wiki_structures.json'), 'structures')
    deliveries = Counter(a.get('delivery') or 'unknown' for page in wiki for a in page.get('attacks') or [])
    summary = catalog['summary']
    kinds = Counter('projectile' if a['role'] == 'projectile_settings' else 'explosion' if
        a['role'].startswith('explosion_settings') else 'damage' for c in catalog['classes'] for a in c['attacks'])
    return {'wikiEnemyPages': len(wiki), 'wikiStructurePages': len(structures),
        'runtimeClasses': summary['classes'], 'runtimeEnemies': summary['enemies'],
        'runtimeStructures': summary['structures'], 'wikiNamed': summary['wikiNamed'],
        'classesWithCandidates': summary['withWikiCandidates'],
        'unresolvedWikiPages': len(catalog['unresolvedWikiPages']),
        'healthFields': summary['fieldInstances'] - summary['attackFieldInstances'],
        'writableFields': summary['writableFieldInstances'], 'attacks': summary['attacks'],
        'classesWithAttacks': summary['classesWithAttacks'], 'attackFields': summary['attackFieldInstances'],
        'attackRowsByKind': dict(sorted(kinds.items())),
        'wikiAttacksByDelivery': dict(sorted(deliveries.items())),
        'wikiRangedAttacksMatchedExactly': research['wikiRangedAttacksMatched'],
        'wikiRangedAttacksWithNineValues': research['wikiRangedAttacks'],
        'notMapped': ['melee and ability attacks (no mount chain)', 'death explosions', 'beams (Harvester)',
            'movement, detection and AI members (deliberately not attempted)']}


def other_audit():
    throwables = load(SDK / 'ThrowableAuthoringCapabilities.json')['summary']
    boosters = load(SDK / 'BoosterAuthoringCapabilities.json')['summary']
    vehicles = load(SDK / 'VehicleAuthoringCapabilities.json')['summary']
    status = load(SDK / 'StatusEffectCatalog.json')['summary']
    wiki_throwables = len(items(load(WIKI / 'wiki_throwables.json'), 'throwables'))
    wiki_boosters = len(items(load(WIKI / 'wiki_boosters.json'), 'boosters'))
    wiki_vehicles = len(items(load(WIKI / 'wiki_vehicle_stratagems.json'), 'stratagems'))
    return {'throwables': {'wiki': wiki_throwables, 'runtime': throwables['throwables'],
            'writable': throwables['writableThrowables'], 'writableFields': throwables['writableFieldInstances']},
        'boosters': {'wiki': wiki_boosters, 'runtime': boosters['boosters'], 'writable': boosters['writableBoosters'],
            'fields': boosters['fieldInstances']},
        'vehicles': {'wiki': wiki_vehicles, 'runtime': vehicles['vehicles'], 'writableFields':
            vehicles['writableFieldInstances'], 'mountedWeaponsDiscovered': vehicles['discoveredMountedWeapons']},
        'statusEffects': {'catalogued': status['statuses'], 'attachable': status['attachable']}}


def build():
    return {'schemaVersion': 1, 'build': 'F5FEE03DCFDB', 'writes': 0,
        'method': 'Reviewed map from each wiki stat to the Runtime semantic fields that author it; a stat is covered '
            'when a writable field exists, whatever its number.',
        'stratagems': stratagem_audit(),
        'supportWeapons': weapon_audit('wiki_support_weapons.json', support_rows()),
        'playerWeapons': weapon_audit('wiki_player_weapons.json', player_rows()),
        'enemies': enemy_audit(), 'other': other_audit(), 'outputFamilies': family_audit(),
        'nativeOnlyCandidates': CANDIDATES}


def percent(counts):
    return f"{counts['covered']}/{counts['stated']}" + (f" ({100 * counts['covered'] // counts['stated']}%)"
        if counts['stated'] else '')


def markdown(report):
    s, sw, pw, e, o, f = (report[k] for k in ('stratagems', 'supportWeapons', 'playerWeapons', 'enemies', 'other',
        'outputFamilies'))
    lines = ['# Runtime coverage audit (build F5FEE03DCFDB)', '',
        'Generated by `scripts/audit_runtime_coverage.py` from the scraped wiki datasets and the generated Runtime '
        'catalogs (`research/runtime-coverage-audit-F5FEE03DCFDB.json` has every row).',
        '',
        '- **Method.** A reviewed map ties each wiki stat to the Runtime semantic fields that author it. A stat is '
        '"covered" when a writable field exists for that item.',
        '- **The wiki is a guide only.** Coverage never depends on the wiki\'s number agreeing, and no field was '
        'exposed because of this audit.', '',
        '## Summary', '',
        '| Family | Wiki items | Resolved in Runtime | With writable fields |', '| --- | --- | --- | --- |',
        f"| Stratagems | {s['wikiStratagems']} | {s['resolved']} | {s['withWritableFields']} |",
        f"| Support weapons | {sw['wikiWeapons']} | {sw['resolved']} | {sw['withWritableFields']} |",
        f"| Player weapons | {pw['wikiWeapons']} | {pw['resolved']} | {pw['withWritableFields']} |",
        f"| Throwables | {o['throwables']['wiki']} | {o['throwables']['runtime']} | {o['throwables']['writable']} |",
        f"| Boosters | {o['boosters']['wiki']} | {o['boosters']['runtime']} | {o['boosters']['writable']} |",
        f"| Vehicles | {o['vehicles']['wiki']} | {o['vehicles']['runtime']} (incl. native-only) | {o['vehicles']['runtime']} |",
        f"| Enemies | {e['wikiEnemyPages']} pages | {e['runtimeEnemies']} native classes | {e['runtimeEnemies']} |",
        f"| Structures | {e['wikiStructurePages']} pages | {e['runtimeStructures']} native classes | {e['runtimeStructures']} |",
        f"| Status effects | — | {o['statusEffects']['catalogued']} catalogued | {o['statusEffects']['attachable']} attachable |",
        '', '## Stratagems (A)', '',
        '| Wiki stat | Covered / stated | Note |', '| --- | --- | --- |']
    for stat, counts in s['statCoverage'].items():
        lines.append(f"| `{stat}` | {percent(counts)} | {counts.get('note') or ''} |")
    families = defaultdict(list)
    for row in s['stratagems']:
        families[row['family'] or 'other'].append(row)
    lines += ['', '| Family | Stratagems | Resolved | Writable domains (union) |', '| --- | --- | --- | --- |']
    for family, rows in sorted(families.items()):
        domains = sorted({d for r in rows for d in r['writableDomains']})
        lines.append(f"| {family} | {len(rows)} | {sum(r['resolved'] for r in rows)} | {', '.join(domains)} |")
    unresolved = [r['name'] for r in s['stratagems'] if not r['resolved']]
    lines += ['', f"Unresolved wiki stratagems ({len(unresolved)}): " + (', '.join(unresolved) or 'none') + '.']
    lines += ['', 'Notes:',
        '- Mission and objective stratagems have no resolved Runtime root. Examples: Reinforce, Resupply, SoS '
        'Beacon, Hellbomb, SEAF Artillery, drills and flags.',
        '- Vehicle and backpack rows include the fields of `sdk/VehicleAuthoringCapabilities.json`, '
        '`sdk/VehicleWeaponCapabilities.json` and `sdk/BackpackAuthoringCapabilities.json`.',
        f"- {len(s['runtimeOnly'])} Runtime stratagems are support-weapon call-ins. The wiki describes them on the "
        'support-weapon pages, audited below.']
    for title, block in (('Support weapons (B)', sw), ('Player weapons', pw)):
        lines += ['', f'## {title}', '', '| Wiki stat | Covered / stated | Note |', '| --- | --- | --- |']
        for stat, counts in block['statCoverage'].items():
            lines.append(f"| `{stat}` | {percent(counts)} | {counts.get('note') or ''} |")
        gaps = Counter(stat for row in block['weapons'] for stat in row['uncoveredStats'])
        worst = [r for r in block['weapons'] if r['uncoveredStats']]
        lines += ['', f"Weapons with at least one uncovered stated stat: {len(worst)} of {block['wikiWeapons']}. Most "
            f"common gaps: " + ', '.join(f'`{k}` ({v})' for k, v in gaps.most_common(6)) + '.']
    lines += ['', '## Enemies and structures (E, F, G)', '',
        f"- Wiki pages: {e['wikiEnemyPages']} enemies and {e['wikiStructurePages']} structures.",
        f"- Runtime classes: {e['runtimeClasses']} ({e['runtimeEnemies']} enemies, {e['runtimeStructures']} structures).",
        f"- Wiki-named by exact anatomy: {e['wikiNamed']}; with anatomy candidates: {e['classesWithCandidates']}; "
        f"wiki pages without a proven class: {e['unresolvedWikiPages']}.",
        f"- Fields: {e['healthFields']} health / zone fields, {e['attackFields']} attack fields, {e['writableFields']} "
        "writable in total.",
        f"- Attacks: {e['attacks']} mounted-weapon settings rows on {e['classesWithAttacks']} classes "
        f"({e['attackRowsByKind'].get('damage', 0)} DamageInfo, {e['attackRowsByKind'].get('projectile', 0)} "
        f"ProjectileSettings, {e['attackRowsByKind'].get('explosion', 0)} ExplosionSettings).",
        f"  {e['wikiRangedAttacksMatchedExactly']} of the {e['wikiRangedAttacksWithNineValues']} wiki ranged attacks "
        "that state all nine values are matched exactly by a class's own row.",
        '- Wiki attacks by delivery: ' + ', '.join(f'{k} {v}' for k, v in e['wikiAttacksByDelivery'].items()) + '.',
        '- Not mapped: ' + '; '.join(e['notMapped']) + '.',
        '', '## Output families (H)', '',
        '| Catalog | ' + ' | '.join(FAMILY_DOMAINS) + ' |', '| --- |' + ' --- |' * len(FAMILY_DOMAINS)]
    for name, counts in f['writableFieldsByCatalog'].items():
        lines.append(f'| {name} | ' + ' | '.join(str(counts.get(d, '—')) for d in FAMILY_DOMAINS) + ' |')
    lines += ['', '`statusSlot` counts the DamageInfo status slots (which status a hit applies). `status` counts '
        "status definitions (a status's duration and its own tick damage).", '', 'Gaps:']
    lines += [f"- **{g['family']}**: {g['detail']}" for g in f['gaps']]
    lines += ['', '## Native-only candidates (J), ranked', '',
        'None of these is exposed writable. Each needs the listed proof first.', '',
        '| Rank | Member | Where | Evidence so far | Missing proof | Risk |', '| --- | --- | --- | --- | --- | --- |']
    for c in report['nativeOnlyCandidates']:
        lines.append(f"| {c['rank']} | {c['member']} | {c['where']} | {c['evidence']} | {c['missing']} | {c['risk']} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='fail if the outputs are stale')
    args = parser.parse_args(argv)
    report = build()
    outputs = {JSON_OUTPUT: json.dumps(report, indent=1) + '\n', MD_OUTPUT: markdown(report)}
    stale = [path for path, body in outputs.items()
        if not path.exists() or path.read_text(encoding='utf-8') != body]
    if args.check:
        if stale:
            raise SystemExit('stale coverage audit: ' + ', '.join(map(str, stale)))
        return
    for path, body in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8', newline='\n')
    print(json.dumps({k: report['stratagems'][k] for k in ('wikiStratagems', 'resolved', 'withWritableFields')}))


if __name__ == '__main__':
    main()
