"""Resolve the 23 throwable-slot items to native identities and map their authorable native graph.

Offline research; nothing here writes memory. Inputs: the retained F5FEE03DCFDB snapshot (live entity and
settings tables, read through the production discovery path), the pinned type library, and the wiki throwable
catalog (HD2WikiImporter/output/wiki_throwables.json) as value fingerprints only.

Identity. Candidates are every entity owning a ThrowableComponent. Each wiki item is compared, fact by fact,
with each candidate's native values:

- inventory counts (ThrowableComponent +100/+104/+108);
- detonation mode, fuse and cookability (ExplosiveComponent);
- the explosion row and its DamageInfo (damage, durable, penetration, radii, demolition, stagger, push);
- shrapnel and bomblet counts;
- the direct-hit DamageInfo;
- shield capacity and radius;
- mine health.

An item resolves only when exactly one candidate agrees with every published fact and no other item claims
that candidate. Resource path names are recorded as supporting evidence only.

Native graph (typed members only):

- ThrowableComponent (+100 start amount, +104 max amount, +108 refill amount);
- ExplosiveComponent (+0 ExplosiveMode, +8 arming delay, +12 explosion delay, +36 ExplosionType,
  +40 impact ExplosionType, +252 timed status template);
- StickyComponent (+44 DamageInfoType, direct hit);
- ShieldComponent;
- HealthComponent;
- explosion row (+4 DamageInfoType, +80 shrapnel count, +84 shrapnel ProjectileType);
- projectile row (+60 DamageInfoType, +144/+156 ExplosionType);
- DamageInfo status slots (+44 + 8n StatusEffectType, +48 + 8n strength);
- StatusEffectSettings.

Shared scope. Every member of every component and settings layout whose type is one of the ExplosionType,
DamageInfoType, ProjectileType or StatusEffectType enums is indexed. A settings row's known consumers are all the
records that reference it. Settings rows are global definitions, so every settings-row field requires
allow_shared.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)
from reference_format import dl_hash, find_component  # noqa: E402

WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_throwables.json'
OUTPUT = ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json'
ENUMS = {dl_hash('ExplosionType'): 'explosion', dl_hash('DamageInfoType'): 'damage',
    dl_hash('ProjectileType'): 'projectile', dl_hash('StatusEffectType'): 'status'}
AP_LABELS = {'Unarmored': 0, 'Light': 2, 'Medium': 3, 'Heavy': 4, 'Anti-Tank I': 5, 'Tank I': 5,
    'Anti-Tank II': 6, 'Tank II': 6, 'Anti-Tank III': 7, 'Tank III': 7, 'Anti-Tank IV': 8, 'Anti-Tank V': 9}
# ExplosiveComponent.Mode values, correlated 23/23 with the wiki trigger and cookable columns.
MODES = {0: 'timed_cookable', 2: 'armed_on_throw', 3: 'sticky_timed_cookable', 4: 'proximity'}
UNVERIFIED = ('Natively proven owner and exact wiki fingerprint, but no in-game test has confirmed the effect of '
    'a changed value.')
SHARED_SETTINGS = ('Settings rows are global definitions; other consumers, including code-selected ones, cannot '
    'be excluded, so every settings-row edit requires allow_shared.')


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def i32(b, o):
    return struct.unpack_from('<i', b, o)[0]


def f32(b, o):
    return float(f'{struct.unpack_from("<f", b, o)[0]:.7g}')


def hexid(value):
    return f'0x{value:016X}'


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


class Native:
    def __init__(self):
        from migration import build_view as bv
        import research_entity_authoring as rea
        self.view = bv.from_snapshot(build_profile.SNAPSHOT)
        self.paths = rea.Native()
        self.library = self.view.library
        self.entities = None

    def component(self, name, resource):
        return self.view.record(name, resource)

    def settings(self, kind, record_type):
        table = self.view.settings_table(kind)
        rows = table.row_for_type(record_type) if table and record_type else []
        if len(rows) != 1:
            return None
        return {'kind': kind, 'recordType': record_type, 'group': table.group, 'row': rows[0][0], 'bytes': rows[0][1]}

    def path(self, resource):
        return self.paths.path(resource)

    # ---- typed reference index -----------------------------------------------------------------------------
    def enum_members(self, type_hash, base=0, depth=0):
        """(offset, kind) for every typed reference member, recursing into structs and inline arrays."""
        layout = self.view.layout(type_hash)
        found = []
        if layout is None or depth > 6:
            return found
        for member in layout.members:
            count = member['count'] if member['atom'] == 'INLINE_ARRAY' else 1
            if member['storage'].startswith('ENUM_') and member['typeHash'] in ENUMS and member['size'] >= 4:
                stride = member['size'] // max(count, 1)
                found += [(base + member['offset'] + i * stride, ENUMS[member['typeHash']]) for i in range(count)]
            elif member['storage'] == 'STRUCT':
                nested = self.view.layout(member['typeHash'])
                if nested is None:
                    continue
                stride = member['size'] // max(count, 1)
                for i in range(count):
                    found += self.enum_members(member['typeHash'], base + member['offset'] + i * stride, depth + 1)
        return found

    def reference_index(self):
        """{(kind, type): [consumer...]} over every entity component table and settings row."""
        index = {}
        names = [line for line in (build_profile.FILEDIVER / 'hashes/dl_type_names.txt').read_text(
            encoding='utf-8').splitlines() if line.endswith('ComponentData')]
        entities = (build_profile.datalibrary() / 'generated_entities.dl_bin').read_bytes()
        tables = 0
        for name in sorted(set(names)):
            try:
                _, body, _, _, _ = find_component(entities, name)
                outer = self.library.layout(name)
            except ValueError:
                continue
            if len(outer['members']) != 2:
                continue                                           # not an index + record-array component
            ids, records = outer['members']
            members = self.enum_members(records['type_hash'])
            if not members:
                continue
            tables += 1
            size = records['size64'] // max(records['array_or_bits'], 1)
            owners = {}
            for row in range(ids['array_or_bits']):
                resource, record, _ = struct.unpack_from('<QII', body, ids['offset64'] + row * 16)
                if resource:
                    owners.setdefault(record, []).append(resource)
            for record, resources in owners.items():
                raw = body[records['offset64'] + record * size:records['offset64'] + (record + 1) * size]
                for offset, kind in members:
                    value = u32(raw, offset)
                    if value:
                        index.setdefault((kind, value), []).append({'component': name, 'recordIndex': record,
                            'offset': offset, 'owners': sorted(resources)})
        for kind in ('projectile', 'damage', 'explosion', 'arc', 'beam', 'status'):
            table = self.view.settings_table(kind)
            if table is None:
                continue
            for group in table.groups.values():
                members = self.enum_members(group.layout.type_hash)
                for row, record_type, raw in group.rows:
                    for offset, ref_kind in members:
                        if offset == 0 and ref_kind == kind:
                            continue                               # the row's own type
                        value = u32(raw, offset)
                        if value:
                            index.setdefault((ref_kind, value), []).append({'settings': kind,
                                'recordType': record_type, 'offset': offset})
        self.tables_indexed = tables
        return index


def wiki_facts(item):
    """Published values the native graph must reproduce (None where the wiki has no value)."""
    counts = item['counts']
    effect = item.get('primaryEffect') or {}
    attack = effect.get('attack') or {}
    damage = attack.get('damage') or {}
    area = attack.get('areaOfEffect') or {}
    special = attack.get('specialEffects') or {}
    pen = attack.get('penetration') or {}

    def v(node):
        return node.get('value') if isinstance(node, dict) else None
    fuses = [f['value'] for f in item['detonation']['fuseSeconds']]
    return {'starting': v(counts.get('starting')), 'maximum': v(counts.get('maximum')),
        'fromSupply': v(counts.get('fromSupply')), 'trigger': item['detonation']['trigger'], 'fuses': fuses,
        'cookable': item['detonation']['cookable'], 'sticky': item['detonation']['sticky'],
        'role': effect.get('role'), 'damage': v(damage.get('standard')), 'durable': v(damage.get('durable')),
        'ap': v(pen.get('inner')) if pen.get('inner') else v(pen.get('direct')),
        'apSlight': v(pen.get('slightAngle')), 'apLarge': v(pen.get('largeAngle')),
        'apExtreme': v(pen.get('extremeAngle')),
        'inner': v(area.get('innerRadiusMeters')), 'outer': v(area.get('outerRadiusMeters')),
        'shockwave': v(area.get('shockwaveRadiusMeters')), 'demolition': v(special.get('demolitionForce')),
        'stagger': v(special.get('staggerForce')), 'push': v(special.get('pushForce')),
        'children': [(c.get('name'), c.get('role'), c.get('relationship')) for c in effect.get('children') or []],
        'shield': item.get('shield'), 'deployed': item.get('deployedEntity')}


def status_labels(item):
    labels = []
    effect = item.get('primaryEffect') or {}
    for child in effect.get('children') or []:
        if child.get('role') == 'Status':
            labels.append(child['name'])
    for child in item.get('secondaryEffects') or []:
        if child.get('role') == 'Status':
            labels.append(child['name'])
    return labels


def damage_values(row):
    b = row['bytes']
    return {'damage': i32(b, 4), 'durable': i32(b, 8), 'ap': [u32(b, 12 + 4 * i) for i in range(4)],
        'demolition': u32(b, 28), 'stagger': u32(b, 32), 'push': u32(b, 36), 'element': u32(b, 40),
        'status': [{'slot': i, 'type': u32(b, 44 + 8 * i), 'strength': f32(b, 48 + 8 * i)}
            for i in range(4) if u32(b, 44 + 8 * i)]}


def explosion_values(row):
    b = row['bytes']
    return {'damageType': u32(b, 4), 'inner': f32(b, 16), 'outer': f32(b, 20), 'shockwave': f32(b, 24),
        'shrapnelCount': u32(b, 80), 'shrapnelProjectile': u32(b, 84)}


def projectile_values(row):
    b = row['bytes']
    return {'velocity': f32(b, 32), 'mass': f32(b, 36), 'drag': f32(b, 40), 'gravity': f32(b, 44),
        'damageType': u32(b, 60), 'impact': u32(b, 144), 'expiry': u32(b, 156)}


def candidate_graph(native, resource):
    """Everything the identity comparison and field mapping need for one ThrowableComponent owner."""
    graph = {'resource': resource, 'path': native.path(resource), 'entityRow': native.view.entity_rows.get(resource)}
    throwable = native.component('ThrowableComponentData', resource)
    t = throwable['bytes']
    graph['throwable'] = {'record': throwable, 'starting': u32(t, 100), 'maximum': u32(t, 104),
        'fromSupply': u32(t, 108)}
    graph['loadout'] = native.component('LoadoutPackageComponentData', resource) is not None
    # Player armory equipment owns an encyclopedia entry (the thermite's AI-thrown twin has none).
    graph['armory'] = native.paths.component(hexid(resource), 'EncyclopediaEntryComponentData') is not None
    graph['aiBehavior'] = native.paths.component(hexid(resource), 'BehaviorComponentData') is not None
    explosive = native.component('ExplosiveComponentData', resource)
    if explosive:
        e = explosive['bytes']
        graph['explosive'] = {'record': explosive, 'mode': i32(e, 0), 'arming': f32(e, 8), 'delay': f32(e, 12),
            'explosion': u32(e, 36), 'impactExplosion': u32(e, 40),
            'timedStatus': [{'type': u32(e, 256 + 8 * i), 'value': f32(e, 260 + 8 * i)} for i in range(4)
                if u32(e, 256 + 8 * i)], 'timedStatusTemplate': e[252:308].hex()}
        row = native.settings('explosion', graph['explosive']['explosion'])
        if row:
            graph['explosion'] = dict(row, values=explosion_values(row))
            damage = native.settings('damage', graph['explosion']['values']['damageType'])
            if damage:
                graph['explosionDamage'] = dict(damage, values=damage_values(damage))
            projectile = native.settings('projectile', graph['explosion']['values']['shrapnelProjectile'])
            if projectile and graph['explosion']['values']['shrapnelCount']:
                graph['submunition'] = dict(projectile, values=projectile_values(projectile))
                sub = graph['submunition']['values']
                sub_damage = native.settings('damage', sub['damageType'])
                if sub_damage:
                    graph['submunitionDamage'] = dict(sub_damage, values=damage_values(sub_damage))
                if sub['impact'] or sub['expiry']:
                    if sub['impact'] != sub['expiry'] and sub['impact'] and sub['expiry']:
                        graph['submunitionExplosionConflict'] = [sub['impact'], sub['expiry']]
                    child = native.settings('explosion', sub['impact'] or sub['expiry'])
                    if child:
                        graph['submunitionExplosion'] = dict(child, values=explosion_values(child))
                        child_damage = native.settings('damage', graph['submunitionExplosion']['values']['damageType'])
                        if child_damage:
                            graph['submunitionExplosionDamage'] = dict(child_damage, values=damage_values(child_damage))
    statuses = {}
    for key in ('explosionDamage',):
        for slot in ((graph.get(key) or {}).get('values') or {}).get('status', []):
            row = native.settings('status', slot['type'])
            if row:
                statuses[str(slot['type'])] = dict(row, duration=f32(row['bytes'], 40))
    if statuses:
        graph['statusDefinitions'] = statuses
    sticky = native.component('StickyComponentData', resource)
    if sticky:
        graph['sticky'] = {'record': sticky, 'damageType': u32(sticky['bytes'], 44)}
        direct = native.settings('damage', graph['sticky']['damageType'])
        if direct:
            graph['directDamage'] = dict(direct, values=damage_values(direct))
    shield = native.component('ShieldComponentData', resource)
    if shield:
        s = shield['bytes']
        graph['shield'] = {'record': shield, 'radius': f32(s, 0), 'durability': f32(s, 76),
            'delayA': f32(s, 88), 'delayB': f32(s, 92)}
    health = native.component('HealthComponentData', resource)
    if health:
        graph['health'] = {'record': health, 'health': i32(health['bytes'], 0)}
    return graph


def compare(facts, graph):
    """(matched, mismatched) fact lists for one wiki item against one candidate."""
    matched, mismatched = [], []

    def check(label, published, native, tolerance=1e-3):
        if published is None:
            return
        same = native is not None and abs(float(published) - float(native)) <= tolerance
        (matched if same else mismatched).append({'fact': label, 'wiki': published, 'native': native})
    check('counts.starting', facts['starting'], graph['throwable']['starting'])
    check('counts.maximum', facts['maximum'], graph['throwable']['maximum'])
    check('counts.fromSupply', facts['fromSupply'], graph['throwable']['fromSupply'])
    explosive = graph.get('explosive')
    trigger = facts['trigger']
    if explosive:
        native_trigger = {0: 'Timed', 3: 'Timed', 4: 'Proximity'}.get(explosive['mode'])
        if explosive['mode'] == 2:
            native_trigger = 'Timed' if explosive['delay'] > 0 else 'Impact'
        if trigger in ('Timed', 'Impact', 'Proximity'):
            (matched if native_trigger == trigger else mismatched).append(
                {'fact': 'detonation.trigger', 'wiki': trigger, 'native': MODES.get(explosive['mode'])})
        if facts['cookable'] is not None:
            (matched if facts['cookable'] == (explosive['mode'] in (0, 3)) else mismatched).append(
                {'fact': 'detonation.cookable', 'wiki': facts['cookable'], 'native': MODES.get(explosive['mode'])})
        if trigger == 'Timed' and facts['fuses'] and explosive['mode'] in (0, 2):
            check('detonation.fuse', facts['fuses'][0], explosive['delay'])
    elif trigger not in (None, 'None'):
        mismatched.append({'fact': 'detonation.trigger', 'wiki': trigger, 'native': None})
    if facts['role'] == 'Explosion':
        explosion, damage = graph.get('explosion'), graph.get('explosionDamage')
        values = explosion['values'] if explosion else {}
        dv = damage['values'] if damage else {}
        check('explosion.inner_radius', facts['inner'], values.get('inner'))
        check('explosion.outer_radius', facts['outer'], values.get('outer'))
        check('explosion.shockwave_radius', facts['shockwave'], values.get('shockwave'))
        check('explosion.damage.standard_damage', facts['damage'], dv.get('damage'))
        check('explosion.damage.durable_damage', facts['durable'], dv.get('durable'))
        check('explosion.damage.ap', facts['ap'], (dv.get('ap') or [None])[0])
        check('explosion.damage.demolition', facts['demolition'], dv.get('demolition'))
        check('explosion.damage.stagger', facts['stagger'], dv.get('stagger'))
        check('explosion.damage.push_force', facts['push'], dv.get('push'))
    elif facts['role'] == 'Damage':
        dv = (graph.get('directDamage') or {}).get('values') or {}
        check('damage.standard_damage', facts['damage'], dv.get('damage'))
        check('damage.durable_damage', facts['durable'], dv.get('durable'))
        check('damage.ap_direct', facts['ap'], (dv.get('ap') or [None])[0])
        check('damage.demolition', facts['demolition'], dv.get('demolition'))
        check('damage.stagger', facts['stagger'], dv.get('stagger'))
        check('damage.push_force', facts['push'], dv.get('push'))
    for name, role, relationship in facts['children']:
        count = re.search(r'x(\d+)$', name or '')
        if role in ('Shrapnel', 'Bomblet'):
            native_count = (graph.get('explosion') or {}).get('values', {}).get('shrapnelCount')
            published = int(count.group(1)) if count else None
            if published is not None:
                check('explosion.shrapnel_count', published, native_count)
    shield = facts['shield']
    if shield:
        check('shield.durability', (shield.get('capacity') or {}).get('value'), (graph.get('shield') or {}).get('durability'))
        check('shield.radius', (shield.get('radius') or {}).get('value'), (graph.get('shield') or {}).get('radius'))
    deployed = facts['deployed']
    if deployed and (deployed.get('mainHealth') or {}).get('value') is not None:
        check('entity.health', deployed['mainHealth']['value'], (graph.get('health') or {}).get('health'))
    return matched, mismatched


def shrapnel_counts(item):
    """Shrapnel / bomblet counts published in the wiki effect tree ('... x35')."""
    result = []
    for child in (item.get('primaryEffect') or {}).get('children') or []:
        match = re.search(r'x(\d+)', json.dumps(child.get('attack') or {}))
        if child.get('role') in ('Shrapnel', 'Bomblet'):
            result.append(child)
    return result


def build():
    wiki = json.loads(WIKI.read_text(encoding='utf-8'))
    native = Native()
    references = native.reference_index()
    owners = sorted(native.view.component('ThrowableComponentData').owners)
    graphs = {resource: candidate_graph(native, resource) for resource in owners}

    # Wiki shrapnel counts are in the CSV-style child strings ("Shrapnel:AC-8 P2 x35"); rebuild them.
    csv = {}
    for line in (WIKI.parent / 'wiki_throwables.csv').read_text(encoding='utf-8').splitlines()[1:]:
        cols = line.split(',')
        csv[cols[0]] = cols[24]

    catalog, claims = [], {}
    for item in wiki['throwables']:
        facts = wiki_facts(item)
        facts['children'] = [(part.split(':', 1)[1] if ':' in part else part, part.split(':', 1)[0], None)
            for part in csv.get(item['name'], '').split('|') if part]
        results = []
        for resource, graph in graphs.items():
            if not (graph['armory'] and graph['loadout']):
                continue                                       # only player armory equipment can be a slot item
            matched, mismatched = compare(facts, graph)
            results.append((len(mismatched), -len(matched), resource, matched, mismatched))
        results.sort()
        perfect = [r for r in results if r[0] == 0 and -r[1] >= 3]
        best = max((-r[1] for r in perfect), default=0)
        winners = [r for r in perfect if -r[1] == best]
        entry = {'name': item['name'], 'category': item['category'], 'family': item['family'],
            'designation': item['designation'], 'wikiRevision': item.get('wikiRevisionId'),
            'traits': item.get('traits'), 'statusLabels': status_labels(item), 'facts': facts}
        if len(winners) == 1:
            _, _, resource, matched, _ = winners[0]
            runner = next((r for r in results if r[2] != resource), None)
            entry['identity'] = {'status': 'RESOLVED', 'resource': resource, 'matchedFacts': matched,
                'candidatesCompared': len(results), 'throwableComponentOwners': len(graphs),
                'otherPerfectCandidatesOutsideArmory': [graphs[r]['path'] or 'unnamed AI variant' for r, g in
                    graphs.items() if r != resource and not (g['armory'] and g['loadout'])
                    and not compare(facts, g)[1] and len(compare(facts, g)[0]) >= best],
                'nearestOtherCandidate': {'path': graphs[runner[2]]['path'], 'mismatches': runner[0],
                    'matches': -runner[1]} if runner else None}
            claims.setdefault(resource, []).append(item['name'])
        else:
            entry['identity'] = {'status': 'AMBIGUOUS' if winners else 'UNRESOLVED',
                'candidates': [{'path': graphs[r[2]]['path'], 'matches': -r[1], 'mismatches': r[4]}
                    for r in (winners or results[:3])]}
        catalog.append(entry)
    for entry in catalog:
        resource = entry['identity'].get('resource')
        if resource is not None and len(claims[resource]) > 1:
            entry['identity'] = {'status': 'AMBIGUOUS', 'reason': 'candidate claimed by ' + ', '.join(claims[resource])}

    # Status type <-> wiki status label correlation (must be one-to-one across every resolved item).
    status_names = {}
    for entry in catalog:
        if entry['identity']['status'] != 'RESOLVED':
            continue
        graph = graphs[entry['identity']['resource']]
        types = [s['type'] for s in ((graph.get('explosionDamage') or {}).get('values') or {}).get('status', [])]
        types += [s['type'] for s in (graph.get('explosive') or {}).get('timedStatus', [])]
        labels = [label for label in entry['statusLabels']]
        entry['nativeStatusTypes'] = sorted(set(types))
        if len(set(types)) == 1 and len(set(labels)) == 1:
            status_names.setdefault(types[0], set()).add(labels[0])
    status_names = {t: sorted(labels) for t, labels in status_names.items()}
    return {'native': native, 'graphs': graphs, 'references': references, 'catalog': catalog,
        'statusNames': status_names, 'wikiImportedAt': wiki.get('importedAt'), 'wiki': wiki}


def consumers(references, kind, record_type):
    return references.get((kind, record_type), [])


def root_owners(references, kind, record_type, seen=None):
    """Entity resources that reach a settings row through any chain of typed references."""
    seen = seen if seen is not None else set()
    if (kind, record_type) in seen:
        return set(), 0
    seen.add((kind, record_type))
    owners, orphan = set(), 0
    for item in consumers(references, kind, record_type):
        if 'owners' in item:
            owners.update(item['owners'])
        else:
            found, missing = root_owners(references, item['settings'], item['recordType'], seen)
            owners |= found
            orphan += missing + (0 if found else 1)
    return owners, orphan


def describe_consumers(references, kind, record_type, names):
    """Public scope summary: throwables (by name) and other native entities that reach this row."""
    owners, orphan = root_owners(references, kind, record_type)
    throwables = sorted(names[o] for o in owners if o in names)
    return {'directReferences': len(consumers(references, kind, record_type)), 'rootEntities': len(owners),
        'throwables': throwables, 'otherEntities': len(owners) - len(throwables),
        'settingsOnlyReferences': orphan}


def main():
    result = build()
    graphs, catalog, references = result['graphs'], result['catalog'], result['references']
    names = {e['identity']['resource']: e['name'] for e in catalog if e['identity']['status'] == 'RESOLVED'}

    def jsonable(graph):
        out = {}
        for key, value in graph.items():
            if key == 'statusDefinitions':
                out[key] = {t: {k: (hashlib.sha256(v).hexdigest().upper() if k == 'bytes' else v)
                    for k, v in row.items()} for t, row in value.items()}
                continue
            if isinstance(value, dict):
                value = {k: (v.hex() if isinstance(v, bytes) else
                    ({kk: vv for kk, vv in v.items() if kk != 'bytes'} if isinstance(v, dict) else v))
                    for k, v in value.items()}
                if 'bytes' in value:
                    value['bytesSha256'] = hashlib.sha256(bytes.fromhex(value.pop('bytes'))).hexdigest().upper()
            out[key] = value
        out['resource'] = hexid(graph['resource'])
        return out
    document = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'snapshot': build_profile.SNAPSHOT_NAME,
        'wikiImportedAt': result['wikiImportedAt'], 'modes': MODES,
        'referenceIndex': {'componentTablesWithTypedReferences': result['native'].tables_indexed,
            'references': sum(len(v) for v in references.values())},
        'statusNames': {str(k): v for k, v in sorted(result['statusNames'].items())},
        'catalog': [], 'unmatchedThrowableEntities': []}
    for entry in catalog:
        record = {k: v for k, v in entry.items() if k != 'facts'}
        if entry['identity']['status'] == 'RESOLVED':
            resource = entry['identity']['resource']
            record['identity'] = dict(entry['identity'], resource=hexid(resource))
            graph = graphs[resource]
            record['native'] = jsonable(graph)
            scope = {}
            for key, kind in (('explosion', 'explosion'), ('explosionDamage', 'damage'), ('submunition', 'projectile'),
                    ('submunitionDamage', 'damage'), ('submunitionExplosion', 'explosion'),
                    ('submunitionExplosionDamage', 'damage'), ('directDamage', 'damage')):
                if key in graph:
                    scope[key] = describe_consumers(references, kind, graph[key]['recordType'], names)
            for status in ((graph.get('explosionDamage') or {}).get('values') or {}).get('status', []):
                scope['status:' + str(status['type'])] = describe_consumers(references, 'status', status['type'], names)
            record['scope'] = scope
        record['facts'] = entry['facts']
        document['catalog'].append(record)
    matched = set(names)
    for resource, graph in graphs.items():
        if resource not in matched:
            document['unmatchedThrowableEntities'].append({'path': graph['path'], 'loadoutPackage': graph['loadout'],
                'armoryEntry': graph['armory'], 'aiBehavior': graph['aiBehavior'],
                'counts': [graph['throwable']['starting'], graph['throwable']['maximum'],
                    graph['throwable']['fromSupply']]})
    OUTPUT.write_text(json.dumps(document, indent=1, default=str) + '\n', encoding='utf-8', newline='\n')
    resolved = sum(e['identity']['status'] == 'RESOLVED' for e in catalog)
    print('resolved', resolved, '/', len(catalog))
    for entry in catalog:
        identity = entry['identity']
        print(f"  {entry['name']:24} {identity['status']:10} "
            f"{graphs[identity['resource']]['path'].split('/')[-1] if identity.get('resource') else identity}"
            f"  matched={len(identity.get('matchedFacts', []))}")
    return result


if __name__ == '__main__':
    main()
