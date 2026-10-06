"""Projectile identities: who fires each vanilla projectile type, from the game's own data, compared with an unverified
community hint list. Read-only and offline (the pinned datalibrary of build F5FEE03DCFDB); nothing is written to game
memory.

The hint list (research/leads/reddit-projectile-id-hypotheses.csv: 350 community labels by projectile id) is a lead,
never a source: every name this report gives comes from structural evidence in the game's data, and the hint is only
compared with it.

Evidence, strongest first:

1. ``entity``: an entity component member the type library types as ``ProjectileType`` holds the type: what a weapon
   fires (ProjectileWeapon +0), its magazine round pattern, its rounds feed, the projectile of each charge or heat
   level, an orbital's shell list, an Eagle's payload, the Orbital Laser / Railcannon projectile, a guided missile's
   projectile, a spray weapon's projectile, an objective shell. The owning entity is named from the Runtime's own
   catalogues (player and support weapons, stratagem payloads and deployed entities, enemy classes and the weapons their
   mounts carry, vehicles and their mounted weapons, backpacks, throwables), else from its resource path.
2. ``output``: a catalogued attack output fires the type (research/projectile-components-F5FEE03DCFDB.json).
3. ``submunition``: an explosion row spawns the type as shrapnel (ExplosionSettings +84); the explosion's own users
   (projectile rows' impact / expiry explosions, entity members typed ``ExplosionType``) name it.
4. Package names (the asset packages a donor needs) are leads, not identities.

Each type also records its row's own properties (direct-hit damage and armour penetration, statuses, impact and expiry
explosion, ballistics), so a generic hint ("AP0 BGP", "explosive", "slow lobbing") can be checked against the row.

Hint verdicts: AGREES (the evidence names what the hint names), CONTRADICTED (the evidence names owners and none is
what the hint names), CONSISTENT / INCONSISTENT (a generic hint checked against the row's properties), UNVERIFIED
(no evidence and nothing checkable). A verdict is a mechanical comparison; CONTRADICTED rows are for review.

Outputs: research/projectile-identities-F5FEE03DCFDB.json; research/leads/reddit-projectile-id-hypotheses-reviewed.csv
(the hint file with runtime_verified, runtime_name and comparison_notes filled); `--check` compares instead of writing.
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import tables as T  # noqa: E402
from scan.settings import SettingsView  # noqa: E402

OUTPUT = ROOT / 'research/projectile-identities-F5FEE03DCFDB.json'
HINTS = ROOT / 'research/leads/reddit-projectile-id-hypotheses.csv'
REVIEWED = ROOT / 'research/leads/reddit-projectile-id-hypotheses-reviewed.csv'
DOC = ROOT / 'docs/research/projectile-identities-F5FEE03DCFDB.md'
COMPONENTS = ROOT / 'research/projectile-components-F5FEE03DCFDB.json'
TYPES = 350

# Entity members typed ProjectileType (scan.tables), and what each one means.
ROLES = {
    ('ProjectileWeaponComponentData', '0'): 'fires',
    ('ProjectileWeaponComponentData', '576'): 'projectile member +576',
    ('WeaponMagazineComponentData', '4.0'): 'magazine round pattern',
    ('WeaponMagazineComponentData', '4.128'): 'magazine round pattern',
    ('WeaponRoundsComponentData', '64.0'): 'rounds feed',
    ('WeaponRoundsComponentData', '64.4'): 'rounds feed',
    ('WeaponChargeComponentData', '0[0].4'): 'charge level 1',
    ('WeaponChargeComponentData', '0[1].4'): 'charge level 2',
    ('WeaponChargeComponentData', '0[2].4'): 'charge level 3',
    ('WeaponHeatComponentData', '0[0].4'): 'heat level 1',
    ('WeaponHeatComponentData', '0[1].4'): 'heat level 2',
    ('WeaponHeatComponentData', '0[2].4'): 'heat level 3',
    ('BombardmentComponentData', '64'): 'orbital shell',
    ('EagleComponentData', '24'): 'Eagle payload projectile',
    ('ObjectiveShellComponentData', '0'): 'objective shell',
    ('OrbitalAbilityComponentData', '532'): 'orbital ability projectile',
    ('SeekingMissileComponentData', '176'): 'guided missile projectile',
    ('SprayWeaponComponentData', '196'): 'spray projectile',
}


def hexint(value):
    return int(value, 16) if isinstance(value, str) else int(value)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def catalogue_names(tables):
    """resource -> [(category, name)] from the Runtime's own catalogues (identity, not leads)."""
    names = collections.defaultdict(list)

    def add(resource, category, name):
        if resource in (None, '', 0) or not name:
            return
        entry = (category, name)
        key = hexint(resource)
        if entry not in names[key]:
            names[key].append(entry)

    player = load(ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json')
    for weapon in player['weapons']:
        for resource in weapon.get('resources') or []:
            add(resource, 'player weapon', weapon['name'])
    for weapon in player.get('subweapons') or []:
        for resource in weapon.get('resources') or []:
            add(resource, 'player weapon ' + str(weapon.get('kind') or 'subweapon'), weapon['name'])
    for weapon in load(ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json')['weapons']:
        for resource in (weapon.get('resourceHashes') or []) + [weapon.get('attackOwnerResourceHash')]:
            add(resource, 'support weapon', weapon.get('catalogIdentity'))
    stratagems = load(ROOT / 'schemas/stratagem_authoring_catalog.json')['stratagems']
    for name, entry in stratagems.items():
        for payload in (entry.get('root') or {}).get('payloads') or []:
            add(payload, 'stratagem payload', name)
        deployed = entry.get('deployedEntity') or {}
        add(deployed.get('resource'), 'stratagem deployed entity', name)
    paths = {path: resource for resource, path in tables.paths.items()}
    for enemy in load(ROOT / 'sdk/EnemyAuthoringCapabilities.json')['classes']:
        resource = paths.get((enemy.get('identity') or {}).get('path'))
        label = enemy.get('wikiName') or enemy['className']
        add(resource, 'enemy ' + str(enemy.get('faction') or enemy.get('kind')), label)
    for enemy in load(ROOT / 'research/enemy-attacks-F5FEE03DCFDB.json')['classes']:
        label = enemy.get('wikiName') or enemy['className']
        add(enemy['resource'], 'enemy ' + str(enemy.get('faction')), label)
        for slot in enemy.get('slots') or []:
            add(slot.get('weapon'), 'weapon of enemy ' + str(enemy.get('faction')), label)
    entity = load(ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json')
    for vehicle in entity['vehicles']:
        add(vehicle.get('resource'), 'vehicle', vehicle['name'])
        for slot in (vehicle.get('mount') or {}).get('slots') or []:
            add(slot.get('path'), 'vehicle weapon', '%s %s' % (vehicle['name'], slot.get('attachNodeName') or
                'slot %s' % slot.get('slot')))
    for backpack in entity['backpacks']:
        add(backpack.get('resource'), 'backpack', backpack['name'])
    throwables = load(ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json')['catalog']
    for item in (throwables.values() if isinstance(throwables, dict) else throwables):
        add(((item.get('identity') or {}).get('resource')), 'throwable', item.get('name'))
    # A mounted entity is named by what mounts it (the generic mount records: enemies, vehicles, emplacements), after
    # every owner above is named; then by its own resource path's last part.
    for record in entity['mountRecords']:
        for owner in record.get('owners') or []:
            known = names.get(hexint(owner))
            path = tables.paths.get(hexint(owner))
            label = known[0][1] if known else (path.rsplit('/', 1)[-1] if path else None)
            if not label:
                continue
            for slot in record.get('slots') or []:
                add(slot.get('path'), 'mounted on ' + (known[0][0] if known else 'entity'), label)
    for resource, mounted in entity['mountedEntities'].items():
        path = mounted.get('path')
        if path:
            add(resource, 'mounted weapon', path.rsplit('/', 1)[-1])
    return names


def owner_label(tables, names, resource):
    known = names.get(resource)
    path = tables.paths.get(resource)
    thin = tables.name(resource)
    return {'resource': '0x%016X' % resource, 'names': [{'category': c, 'name': n} for c, n in known or []],
        'path': path, 'internal': thin if thin and thin != path else None}


def typed_members(tables, type_name):
    out = []
    for component in tables.component_names():
        for member in tables.component(component).members():
            if member.type_name == type_name:
                out.append((component, member))
    return out


def entity_references(tables, type_name, limit):
    """value -> [(owner resource, component, member path, owners sharing the record)] for every member typed
    ``type_name`` in every component table."""
    refs = collections.defaultdict(list)
    for component, member in typed_members(tables, type_name):
        table = tables.component(component)
        for record, owners in table.owner_map().items():
            value = T.decode(member, table.raw(record))
            for item in (value if isinstance(value, list) else [value]):
                if isinstance(item, int) and 0 < item <= limit:
                    for owner in owners:
                        refs[item].append((owner, component, member.path, len(owners)))
    return refs


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def row_properties(components_row):
    """The row's own properties from the projectile component catalogue."""
    comps = components_row['components']
    damage = (comps.get('damage') or {}).get('definition') or {}
    explosion = (comps.get('impact_explosion') or {}).get('definition')
    ballistics = (comps.get('ballistics') or {}).get('values') or {}
    statuses = sorted({s['status'] for s in damage.get('statuses') or []}
        | {s['status'] for s in ((explosion or {}).get('damage') or {}).get('statuses') or []})
    ap = damage.get('armorPenetration') or []
    return {'damage': {'standard': damage.get('standard'), 'durable': damage.get('durable'),
            'armorPenetration': ap[0] if ap else None},
        'impactExplosion': None if not explosion else {'type': explosion['type'], 'radii': explosion.get('radii'),
            'standard': (explosion.get('damage') or {}).get('standard'), 'submunition': explosion.get('submunition'),
            'volume': explosion.get('volume')},
        'statuses': statuses, 'speed': ballistics.get('speed'), 'mass': ballistics.get('mass'),
        'gravity': ballistics.get('gravity'), 'diameter': ballistics.get('diameter'), 'unit': components_row['unit'],
        'packages': [p['name'] for p in components_row.get('packages') or []]}


# The hint comparison. Words that describe a projectile rather than name its owner (property words are checked
# against the row instead).
GENERIC = set('''bgp bpp agp basic gun projectile projectiles round rounds shell shells small big tiny another yet weird
bugged invisible slow fast speedy very extremely powerful low high damage push force explosive explode explodes explosion
exploding he plasma energy burning rocket rockets missile grenade shotgun pellet lobbing lingering gravity with without
and the of that a an it its it's or but some more effect hit on in from where comes come idk know think maybe possibly
believe similar version styled style like just really no not actually again third fifth one two this which same above
then fall safety distance moving bit too much lot yellow red blast blasts split into strange noises loud bouncier puffy
shaking blank sounds pew dig digging ground environment debris impact delayed variable medium heavy bomb bombs sticking
flac shockwave aoe aol extreme yield success also randomly something fireworks beautiful makes it'll they they're
straight though doesn't don't have has do does been wth idfc fucking god light mist shroom unused splits basically are
anti counter stun gas napalm fire incendiary acid stripped dead body titans titan bounce bouncy lobbed wall walls
mortar there here why what when how who is are was were be i you we me my your so if at by for to up down out about any
all only still even now ever never thing things stuff lol okay ok wtf three four five six many most least
seems seem looks look probably sure kind sort'''.split())
ALIASES = {
    'automaton': ('cyborg', 'automaton'), 'automatons': ('cyborg', 'automaton'), 'bot': ('cyborg',),
    'terminid': ('bug', 'terminid'), 'terminids': ('bug', 'terminid'), 'bile': ('bile', 'spewer', 'spitter'),
    'illuminate': ('illuminate',), 'mech': ('exosuit', 'exo', 'combatwalker'), 'patriot': ('patriot', 'combatwalker'),
    'seaf': ('seaf',), 'orbital': ('orbital',), 'eagle': ('eagle',), '120': ('120mm',), '380': ('380mm',),
    '500kg': ('500kg',), 'material': ('materiel', 'material'), 'maelstorm': ('maelstrom',), 'fog': ('smoke',),
    'hive': ('hive',), 'lord': ('lord', 'hivelord'),
}


def words(text):
    return re.findall(r"[a-z0-9][a-z0-9'.-]*", text.lower())


def compact(text):
    """Lower case without anything but letters and digits: 'StA-X3 W.A.S.P.' -> 'stax3wasp'."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def named(owner):
    return bool(owner['names'] or owner.get('path') or owner.get('internal'))


def owner_texts(identity):
    """Every name the evidence gives (catalogue names, resource paths, internal names, explosion users), as compact
    strings."""
    parts = []
    for owner in identity['owners']:
        for name in owner['names']:
            parts += [name['category'], name['name']]
        parts += [owner.get('path') or '', owner.get('internal') or '']
    for output in identity['outputs']:
        parts.append(output.get('name') or '')
    for source in identity['submunitionOf']:
        parts += source.get('usedBy') or []
    return [compact(part) for part in parts if part]


def near(token, text):
    """token occurs in text, or differs from one of its words by at most one letter (typos: M90DA / M90A)."""
    if token in text:
        return True
    if len(token) < 4:
        return False
    for start in range(0, max(1, len(text) - len(token) + 2)):
        for length in (len(token) - 1, len(token), len(token) + 1):
            piece = text[start:start + length]
            if len(piece) == length and edit_distance(token, piece) <= 1:
                return True
    return False


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def property_checks(hint, props):
    """Generic hint words checked against the row's own properties: [(claim, passed)]."""
    checks = []
    label = hint.lower()
    for match in re.finditer(r'\bap\s*-?\s*(\d+)', label):
        claimed = int(match.group(1))
        actual = props['damage']['armorPenetration']
        if actual is not None:
            checks.append(('AP%d direct hit' % claimed, actual == claimed))
    if re.search(r'\b(explosive|explode|explodes|exploding|he)\b', label):
        checks.append(('explodes', props['impactExplosion'] is not None))
    statuses = ' '.join(props['statuses'])
    for word, needle in (('burning', 'fire'), ('fire', 'fire'), ('fireball', 'fire'), ('incendiary', 'fire'),
            ('napalm', 'fire'), ('stun', 'stun'), ('ems', 'stun'), ('gas', 'gas'), ('bile', 'acid'), ('acid', 'acid'),
            ('smoke', 'smoke'), ('fog', 'smoke')):
        if re.search(r'\b' + word + r'\b', label):
            checks.append((word, needle in statuses or (needle == 'smoke' and props['impactExplosion'] is not None
                and props['impactExplosion'].get('volume') == 'Smoke')))
    speed = props['speed']
    if speed is not None:
        if re.search(r'\bslow\b', label):
            checks.append(('slow (speed %s)' % speed, speed <= 150))
        if re.search(r'\b(fast|speedy)\b', label):
            checks.append(('fast (speed %s)' % speed, speed >= 400))
    if re.search(r'\b(lobbing|lobbed|gravity|mortar)\b', label) and props['gravity'] is not None:
        checks.append(('high gravity (%s)' % props['gravity'], props['gravity'] >= 2))
    return checks


# Class nouns are part of many names but name no owner on their own ("Small Rocket" names no launcher).
CLASS_NOUNS = set('''rifle gun guns shotgun pistol launcher rocket rockets missile grenade grenades cannon machine sentry
strike barrage turret emplacement mine mines pack backpack shield round rounds shell shells projectile weapon weapons
heavy light standard tier base big small mk equipment content fac weapons_default default primary support secondary
expendable portable variant elite female male bug bugs cyborg cyborgs illuminate'''.split())


def name_vocabulary(names, tables):
    """Every word of a catalogued display name (weapons, stratagems, enemies, vehicles, backpacks, throwables) and the
    aliases, in compact form: the names a hint can use. Internal resource paths and mount names still match owners
    but never make a hint word a name (they hold ordinary words such as left, sound or single)."""
    vocabulary = set(ALIASES)
    for entries in names.values():
        for category, name in entries:
            if category.startswith('mounted') or category == 'vehicle weapon':
                continue
            vocabulary.update(compact(w) for w in re.split(r'[\s/_()\-]+', name.lower()))
    return {w for w in vocabulary if len(w) >= 3 and not w.isdigit() and w not in GENERIC and w not in CLASS_NOUNS}


def name_tokens(hint, vocabulary):
    """The hint's words that name something: in the vocabulary, or within one letter of a vocabulary word of five or
    more letters (typos)."""
    found = []
    for word in words(hint):
        token = compact(word.strip('.'))
        if not token or token in GENERIC or token in CLASS_NOUNS:
            continue
        if token in vocabulary or token in ALIASES:
            found.append(token)
        elif len(token) >= 5 and any(abs(len(v) - len(token)) <= 1 and edit_distance(token, v) <= 1
                for v in vocabulary if len(v) >= 5):
            found.append(token)
    return found


def compare(hint, identity, props, vocabulary):
    """(verdict, reason, checks passed, checks failed): see the module docstring."""
    specific = name_tokens(hint, vocabulary)
    checks = property_checks(hint, props)
    passed = [c for c, ok in checks if ok]
    failed = [c for c, ok in checks if not ok]
    texts = owner_texts(identity)
    # A submunition is named only through an explosion user that carries a name ("projectile 26 impact" alone does not).
    has_names = any(named(o) for o in identity['owners']) or bool(identity['outputs']) or any(
        not re.fullmatch(r'projectile \d+ (impact|expiry)', user) for source in identity['submunitionOf']
        for user in source.get('usedBy') or [])
    has_evidence = bool(identity['owners'] or identity['outputs'] or identity['submunitionOf'])
    if has_evidence and specific and has_names:
        matched, close = [], []
        for word in specific:
            aliases = ALIASES.get(word, (word,))
            if any(alias in text for alias in aliases for text in texts):
                matched.append(word)
            elif any(near(word, text) for text in texts):
                close.append(word)
        if matched:
            return 'AGREES', 'named by the evidence: ' + ', '.join(matched), passed, failed
        if close:
            return 'AGREES', 'named by the evidence up to one letter: ' + ', '.join(close), passed, failed
        return 'CONTRADICTED', 'the evidence names other owners (hint words: ' + ', '.join(specific) + ')', passed, failed
    if has_evidence and not has_names:
        return 'OWNER_UNNAMED', 'an owner is proven but carries no name in the Runtime catalogues or the resource ' \
            'paths', passed, failed
    if checks:
        return ('CONSISTENT' if not failed else 'INCONSISTENT'), 'property check', passed, failed
    return 'UNVERIFIED', ('no structural evidence names it and the hint has nothing checkable' if not has_evidence
        else 'a generic hint with nothing checkable'), passed, failed


def runtime_name(identity):
    """The name our evidence gives: the first catalogued owner per role, else the path, else the submunition."""
    labels = []
    for owner in identity['owners']:
        name = owner['names'][0]['name'] if owner['names'] else (owner.get('path') or owner.get('internal')
            or owner['resource']).rsplit('/', 1)[-1]
        label = '%s (%s)' % (name, owner['role'])
        if label not in labels:
            labels.append(label)
    for output in identity['outputs']:
        label = '%s (attack output)' % output.get('name')
        if output.get('name') and not any(output['name'] in item for item in labels):
            labels.append(label)
    for source in identity['submunitionOf']:
        label = 'shrapnel of explosion %d (%s)' % (source['explosion'], ', '.join(source.get('usedBy')[:2]) or 'unused')
        labels.append(label)
    return '; '.join(labels[:4]) + (' (+%d more)' % (len(labels) - 4) if len(labels) > 4 else '')


def build():
    tables = T.pinned()
    settings = SettingsView(tables)
    names = catalogue_names(tables)
    vocabulary = name_vocabulary(names, tables)
    components = {row['type']: row for row in load(COMPONENTS)['rows']}
    projectile_refs = entity_references(tables, 'ProjectileType', TYPES)
    explosion_refs = entity_references(tables, 'ExplosionType', 10000)
    # The explosions each projectile row spawns, and the shrapnel each explosion spawns.
    explosion_users = collections.defaultdict(list)
    for kind in range(1, TYPES + 1):
        raw = settings.row('projectile', kind)
        if raw is None:
            continue
        for offset, how in ((144, 'impact'), (156, 'expiry')):
            explosion = u32(raw, offset)
            if explosion:
                explosion_users[explosion].append(('projectile', kind, how))
    shrapnel = collections.defaultdict(list)
    explosion_table = settings.table('explosion')
    for _row, record_type, raw in explosion_table.rows:
        submunition, count = u32(raw, 84), u32(raw, 80)
        if 0 < submunition <= TYPES:
            shrapnel[submunition].append({'explosion': record_type, 'count': count})

    # Pass 1: every type's direct owners (entity members) and attack outputs.
    direct = {}
    for kind in range(1, TYPES + 1):
        row = components.get(kind)
        if row is None:
            continue
        owners = []
        for owner, component, path, shared in sorted(set(projectile_refs.get(kind, [])), key=lambda r: (r[1], r[2], r[0])):
            label = owner_label(tables, names, owner)
            label.update({'component': component, 'member': path, 'role': ROLES.get((component, path), component + ' ' + path),
                'recordShared': shared > 1})
            owners.append(label)
        outputs = [{'name': item.get('name'), 'owner': item.get('owner') or item.get('kind'), 'output': item.get('output')}
            for item in row['identities']]
        direct[kind] = (owners, outputs)

    def direct_name(kind):
        """The first catalogued (else path) name of a type's direct owners, for naming what its explosions spawn."""
        owners, outputs = direct.get(kind, ([], []))
        for owner in owners:
            if owner['names']:
                return owner['names'][0]['name']
        for output in outputs:
            if output.get('name'):
                return output['name']
        for owner in owners:
            if owner.get('path'):
                return owner['path'].rsplit('/', 1)[-1]
        return None

    def explosion_used_by(explosion):
        used = []
        for owner, component, path, _shared in explosion_refs.get(explosion, []):
            label = owner_label(tables, names, owner)
            name = label['names'][0]['name'] if label['names'] else (label['path'] or '').rsplit('/', 1)[-1]
            if name:
                used.append('%s (%s)' % (name, component.replace('ComponentData', '')))
        for _kind, projectile, how in explosion_users.get(explosion, []):
            name = direct_name(projectile)
            used.append('projectile %d %s%s' % (projectile, how, ' (%s)' % name if name else ''))
        return sorted(set(used))

    hints = {int(row['projectile_id']): row for row in csv.DictReader(io.StringIO(HINTS.read_text(encoding='utf-8-sig')))}
    rows = []
    for kind in range(1, TYPES + 1):
        row = components.get(kind)
        if row is None:
            continue
        owners, outputs = direct[kind]
        submunition_of = [dict(source, usedBy=explosion_used_by(source['explosion'])) for source in shrapnel.get(kind, [])]
        identity = {'owners': owners, 'outputs': outputs, 'submunitionOf': submunition_of}
        props = row_properties(row)
        tier = ('entity' if owners else 'output' if outputs else 'submunition' if submunition_of
            else 'package' if props['packages'] else 'none')
        hint = hints.get(kind, {}).get('reddit_suggested_label', '')
        verdict, reason, passed, failed = compare(hint, identity, props, vocabulary)
        rows.append({'type': kind, 'row': row['row'], 'evidenceTier': tier, 'runtimeName': runtime_name(identity) or None,
            'identity': identity, 'properties': props,
            'hint': {'label': hint, 'verdict': verdict, 'reason': reason, 'checksPassed': passed, 'checksFailed': failed}})
    summary = {'types': len(rows), 'byTier': dict(collections.Counter(r['evidenceTier'] for r in rows)),
        'byVerdict': dict(collections.Counter(r['hint']['verdict'] for r in rows)),
        'withRuntimeName': sum(1 for r in rows if r['runtimeName'])}
    return {'schemaVersion': 1, 'build': 'F5FEE03DCFDB', 'source': {'datalibrary': 'pinned (scan.tables)',
        'rows': str(COMPONENTS.relative_to(ROOT)), 'hints': str(HINTS.relative_to(ROOT)),
        'hintStatus': 'unverified community hypotheses: compared, never used as a source'},
        'writes': 0, 'protectionChanges': 0, 'summary': summary, 'roles': sorted(set(ROLES.values())), 'types': rows}


def reviewed_csv(report):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['projectile_id', 'reddit_suggested_label', 'source_status', 'runtime_verified', 'runtime_name',
        'comparison_notes'])
    for row in report['types']:
        hint = row['hint']
        verified = {'AGREES': 'True', 'CONTRADICTED': 'False', 'INCONSISTENT': 'False'}.get(hint['verdict'], 'unknown')
        notes = [hint['verdict'] + ': ' + hint['reason'], 'evidence tier ' + row['evidenceTier']]
        props = row['properties']
        notes.append('direct hit %s/%s AP%s' % (props['damage']['standard'], props['damage']['durable'],
            props['damage']['armorPenetration']))
        if props['impactExplosion']:
            notes.append('impact explosion %d' % props['impactExplosion']['type'])
        if props['statuses']:
            notes.append('statuses ' + '/'.join(props['statuses']))
        if hint['checksPassed']:
            notes.append('checks passed: ' + ', '.join(hint['checksPassed']))
        if hint['checksFailed']:
            notes.append('checks failed: ' + ', '.join(hint['checksFailed']))
        writer.writerow([row['type'], hint['label'], 'unverified community hypothesis', verified, row['runtimeName'] or '',
            '; '.join(notes)])
    return out.getvalue()


def cell(text):
    return str(text).replace('|', '/')


def document(report):
    """The human-readable report: method, counts, the contradicted hints and the proven owners without a name."""
    s = report['summary']
    lines = ['# Projectile identities (build F5FEE03DCFDB)', '',
        'Generated by `scripts/research_projectile_identities.py` from `research/projectile-identities-F5FEE03DCFDB.json`.',
        'Read-only and offline. The community hint list (`research/leads/reddit-projectile-id-hypotheses.csv`) is a',
        'lead: every name below comes from the game\'s own data, and the hint is only compared with it. The reviewed',
        'copy of the hint file, with `runtime_verified`, `runtime_name` and `comparison_notes` filled, is',
        '`research/leads/reddit-projectile-id-hypotheses-reviewed.csv`.', '',
        '## Evidence', '',
        '- **entity**: an entity component member typed `ProjectileType` holds the type (what a weapon fires, its',
        '  magazine pattern, rounds feed, charge or heat levels, an orbital\'s shell list, an Eagle\'s payload, a',
        '  missile\'s projectile, a spray, an objective shell). Owners are named from the Runtime catalogues, else',
        '  their resource path.',
        '- **output**: a catalogued attack output fires the type.',
        '- **submunition**: an explosion row spawns the type as shrapnel; the explosion\'s users name it.',
        '- **none**: no structural reference in the data (code-literal types, unused rows).', '',
        '| Evidence tier | Types |', '| --- | --- |']
    lines += ['| %s | %d |' % (tier, count) for tier, count in sorted(s['byTier'].items(), key=lambda x: -x[1])]
    lines += ['', '%d of %d types have a name from the evidence.' % (s['withRuntimeName'], s['types']), '',
        '## Hint verdicts', '',
        '| Verdict | Types | Meaning |', '| --- | --- | --- |']
    meaning = {'AGREES': 'the evidence names what the hint names',
        'CONTRADICTED': 'the evidence names owners, none of them what the hint names (review)',
        'CONSISTENT': 'a descriptive hint whose checkable claims (AP, explosion, statuses, speed, gravity) hold',
        'INCONSISTENT': 'a descriptive hint with a claim the row disproves',
        'OWNER_UNNAMED': 'an owner is proven, but it has no name in the catalogues or the resource paths',
        'UNVERIFIED': 'nothing in the data names it and the hint has nothing checkable'}
    lines += ['| %s | %d | %s |' % (v, c, meaning[v]) for v, c in sorted(s['byVerdict'].items(), key=lambda x: -x[1])]
    lines += ['', '## Contradicted hints', '', '| Type | Hint | Evidence |', '| --- | --- | --- |']
    for row in report['types']:
        if row['hint']['verdict'] == 'CONTRADICTED':
            lines.append('| %d | %s | %s |' % (row['type'], cell(row['hint']['label']), cell(row['runtimeName'])))
    lines += ['', '## Proven owners without a name', '',
        'These types have a structural owner whose resource has no name in the Runtime catalogues and no path in',
        'the hash list (for example unnamed objective shells and stratagem payloads outside the catalogues).', '',
        '| Type | Hint | Owners |', '| --- | --- | --- |']
    for row in report['types']:
        if row['hint']['verdict'] == 'OWNER_UNNAMED':
            lines.append('| %d | %s | %s |' % (row['type'], cell(row['hint']['label']), cell(row['runtimeName'])))
    lines += ['', '## Limits', '',
        '- A type the game spawns from a code literal (some enemy attacks) has no data reference, so it stays',
        '  **none** unless a hint is checkable against its row.',
        '- A verdict is a mechanical comparison of names and properties; it never renames a type. Visual claims',
        '  (colours, "plasma", sounds) are not checkable from the row.',
        '- Names are the evidence\'s: a shared row lists every owner (for example the Eagle gun pods and several',
        '  Eagles fire the same round).', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    report = build()
    text = json.dumps(report, indent=1, sort_keys=True) + '\n'
    review = reviewed_csv(report)
    doc = document(report)
    if args.check:
        stale = [str(p) for p, body in ((OUTPUT, text), (REVIEWED, review), (DOC, doc))
            if not p.exists() or p.read_text(encoding='utf-8') != body]
        if stale:
            raise SystemExit('stale projectile identities: ' + ', '.join(stale))
        print('projectile identities are current')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    REVIEWED.write_text(review, encoding='utf-8', newline='\n')
    DOC.write_text(doc, encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
