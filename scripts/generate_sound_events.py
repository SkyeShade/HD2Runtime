"""Generate the full sound-event catalogue from research/sound-events-F5FEE03DCFDB.json
(research/docs/sound-events-F5FEE03DCFDB.md; docs/sounds.md):

- domains/sound_events.lua: the Runtime's catalogue (runtime/sound_catalogue.lua): every Wwise event of the build by its
  name `<family>/<bank>/<event>`, its banks, kind, range, bus, the game parameters / switch and state groups its sounds
  react to, the weapon-catalogue sounds that post it, whether it acts on the whole sound engine, and the package that
  provides its bank (a stratagem's call-in package or a loadout item's); the game parameters, switch groups and state
  groups of the Init bank with their values;
- sdk/SoundEventCatalogue.json: the same for ModBuilder and mod authors.

Names (evidence only): `<family>` from the bank's content path (`content/audio/<bank>`), or `explosions` when the
event's sounds play on the game's own `explosion` mixer bus; `<bank>` the bank's name in lower case; `<event>` the
event's own Wwise name where a string of the game's code or data hashes to its id, else its id as eight hex digits.
The weapon firing-sound catalogue (domains/weapon_sounds.lua) is unchanged; an event it posts lists those names.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402
# Global effects that leave the sound engine changed after the event: hd2.sounds.play refuses an event with any of them.
from wwise_banks import PERSISTENT  # noqa: E402

RESEARCH = ROOT / 'research/sound-events-F5FEE03DCFDB.json'
LUA_OUTPUT = 'domains/sound_events.lua'
JSON_OUTPUT = 'sdk/SoundEventCatalogue.json'
# The bank's family, by its name (first match). Banks a weapon-catalogue sound uses are weapons unless a rule says
# otherwise.
FAMILY_RULES = (
    (r'^(init|game_init|music_init)$', 'system'),
    (r'^music_', 'music'),
    (r'^(vo_bugs)$', 'enemies'),
    (r'^(vo_|helldiver_standard_vo$|mission_.*_exertions$)', 'voice'),
    (r'^(ui_|intro_logos$)', 'ui'),
    (r'^(cutscenes_|tutorial)', 'cinematics'),
    (r'^stratagems?_', 'stratagems'),
    (r'^wep_gre_', 'throwables'),
    (r'^wep_melee_', 'melee'),
    (r'^(seaf_|foley_seafs$)', 'seaf'),
    (r'^(bots_|cyborg_|bugs_|illuminates_|dropship_illuminate$|weapons_bots$|weapons_illuminate$|foley_bots$|'
     r'foley_bugs$|foley_illuminate$)', 'enemies'),
    (r'^(wep_|wpn_|weapons_)', 'weapons'),
    (r'^vehicle_', 'vehicles'),
    (r'^obj_', 'objectives'),
    (r'^haz_', 'hazards'),
    (r'^env_', 'ambience'),
    (r'^foley_', 'foley'),
    (r'^gore_', 'gore'),
)
# The faction a bank belongs to, by a word of its name.
FACTIONS = ((r'(^|_)(bots?|cyborg|cy)(_|$)', 'automaton'), (r'(^|_)(bugs?)(_|$)', 'terminid'),
    (r'(^|_)(illuminates?|il)(_|$)', 'illuminate'))
FAMILIES = ('weapons', 'throwables', 'melee', 'explosions', 'stratagems', 'vehicles', 'enemies', 'seaf', 'objectives',
    'hazards', 'ambience', 'foley', 'gore', 'voice', 'ui', 'music', 'cinematics', 'system', 'other')
# A multi-bank event's own bank: the first family in this order, then the bank with the fewest events, then by name.
RANK = {f: i for i, f in enumerate(FAMILIES)}
EXPLOSION_BUS = 'explosion'
KINDS = {0: 'one_shot', 1: 'loop', 2: 'unknown'}   # metadata duration type (research/wwise-plugin "metadata")
INFINITE = 1e30
# Loadout-catalogue items whose package listing a bank makes it a weapon bank (package evidence).
WEAPON_ITEMS = ('player_weapon/', 'support_weapon/', 'pickup_support_weapon/')


def bank_slug(row, resource):
    name = row['name']
    if not name:
        return 'bank_' + resource.lower()
    return name.rsplit('/', 1)[-1].lower()


def bank_family(slug, weapon_banks, providers):
    for pattern, family in FAMILY_RULES:
        if re.search(pattern, slug):
            return family
    if slug in weapon_banks or any(p['kind'] == 'catalog' and p['key'].startswith(WEAPON_ITEMS) for p in providers):
        return 'weapons'
    return 'other'


def faction_of(slug):
    for pattern, faction in FACTIONS:
        if re.search(pattern, slug):
            return faction
    return None


def number(value, digits=2):
    if value is None or not math.isfinite(value) or abs(value) >= INFINITE:
        return None
    return round(value, digits)


def weapon_links():
    """Event id (8 hex) -> weapon-catalogue names that post it; bank resources the weapon catalogue uses."""
    import generate_weapon_sounds as gws
    d = gws.build()
    links, banks = collections.defaultdict(list), set()
    for name, s in sorted(d['sounds'].items()):
        for key in ('event', 'start', 'stop'):
            e = s.get(key)
            if e and e != '00000000' and name not in links[e]:
                links[e].append(name)
        for b in s.get('banks') or []:
            banks.add(b)
    return links, banks


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    links, weapon_bank_names = weapon_links()
    weapon_banks = {n.rsplit('/', 1)[-1].lower() for n in weapon_bank_names}
    # Banks.
    banks, bank_index = [], {}
    for resource, row in sorted(research['banks'].items(), key=lambda kv: (bank_slug(kv[1], kv[0]), kv[0])):
        slug = bank_slug(row, resource)
        providers = research['bankProviders'].get(resource, [])
        family = bank_family(slug, weapon_banks, providers)
        provider = None
        for p in providers:
            if p['kind'] == 'stratagem' and p['complete']:
                provider = {'stratagem': p['name'], 'stratagemId': p['stableId'], 'packages': p['packages']}
                break
        if provider is None:
            for p in providers:
                if p['kind'] == 'catalog':
                    provider = {'item': p['key'], 'itemLabel': p['label']}
                    break
        listed = research['bankPackages'].get(resource, [])
        resident = max((research['packages'][p]['residentInSnapshots'] for p in listed), default=0)
        bank_index[resource] = len(banks) + 1
        banks.append({'name': slug, 'resource': resource, 'path': row['name'], 'family': family,
            'faction': faction_of(slug), 'events': row['events'], 'provider': provider, 'packages': len(listed),
            'residentInSnapshots': resident})
    # Busses: the named path of each bus (its named ancestors, outermost first).
    busses = research['busses']

    def bus_path(bus):
        parts, seen = [], set()
        while bus and bus not in seen:
            seen.add(bus)
            row = busses.get(bus)
            if not row:
                break
            if row['name']:
                parts.append(row['name'].lower())
            bus = row['parent']
        return '/'.join(reversed(parts)) or None
    bus_paths = {b: bus_path(b) for b in busses}
    # Names of the Init bank's ids.
    def pname(i):
        row = research['parameters'].get(i)
        return row['name'].lower() if row and row['name'] else None
    # Events.
    event_names = {i: row['name'].lower() for i, row in research['eventNames'].items()}
    events, used = {}, set()
    for i, e in sorted(research['events'].items()):
        own = sorted(e['banks'], key=lambda r: (RANK[banks[bank_index[r] - 1]['family']], research['banks'][r]['events'],
            banks[bank_index[r] - 1]['name'], r))
        primary = banks[bank_index[own[0]] - 1]
        # The bus shown is the explosion bus when one of its sounds plays there, else the first path.
        paths = sorted({bus_paths.get(b) for b in e['busses'] if bus_paths.get(b)},
            key=lambda p: (EXPLOSION_BUS not in p.split('/'), p))
        family = primary['family']
        if any(EXPLOSION_BUS in p.split('/') for p in paths):
            family = 'explosions'
        name = '%s/%s/%s' % (family, primary['name'], event_names.get(i, i.lower()))
        if name in used:
            raise ValueError('duplicate sound event name ' + name)
        used.add(name)
        m = e['metadata']
        if not (e['plays'] or e['nested']):
            kind = 'control'
        else:
            kind = KINDS.get(m[3], 'unknown') if m else 'unknown'
        row = {'id': i, 'banks': [bank_index[r] for r in own], 'kind': kind}
        if m:
            if number(m[0]) and m[0] > 0:
                row['range'] = number(m[0], 1)
            if kind == 'one_shot' and number(m[1]) is not None:
                row['duration'] = number(m[1], 3)
            row['position'] = m[4]
        if e['effects']:
            row['effects'] = e['effects']
            if set(e['effects']) & set(PERSISTENT):
                row['persistent'] = True
        if paths:
            row['bus'] = paths[0]
        if e['parameters']:
            row['parameters'] = e['parameters']
        if e['volumeParameters']:
            row['volume'] = e['volumeParameters']
        if e['switchGroups']:
            row['switchGroups'] = e['switchGroups']
        if e['stateGroups']:
            row['stateGroups'] = e['stateGroups']
        if i in links:
            row['weapons'] = links[i]
        if i in event_names:
            row['wwise'] = event_names[i]
        events[name] = row
    parameters = {i: {'name': pname(i), 'default': number(p['default'], 4), 'events': p['events'],
        'builtIn': p['builtIn']} for i, p in sorted(research['parameters'].items())}
    def group_rows(groups, key):
        out = {}
        for i, g in sorted(groups.items()):
            out[i] = {'name': g['name'].lower() if g['name'] else None,
                'values': {v: (n.lower() if n else False) for v, n in sorted(g[key].items())}}
            if g.get('parameter'):
                out[i]['parameter'] = g['parameter']
        return out
    families = collections.Counter(n.split('/', 1)[0] for n in events)
    return {'source': {'research': RESEARCH.name, 'build': research['build'], 'banksSha256': research['banksSha256']},
        'counts': {'events': len(events), 'banks': len(banks), 'named': len(event_names),
            'byFamily': dict(sorted(families.items())),
            'byKind': dict(sorted(collections.Counter(e['kind'] for e in events.values()).items())),
            'globalEffects': sum(1 for e in events.values() if e.get('effects')),
            'persistentEffects': sum(1 for e in events.values() if e.get('persistent')),
            'parameters': len(parameters), 'namedParameters': sum(1 for p in parameters.values() if p['name']),
            'controlMatches': research['names']['controlMatches']},
        'families': list(FAMILIES), 'banks': banks, 'events': events, 'parameters': parameters,
        'switchGroups': group_rows(research['switchGroups'], 'switches'),
        'stateGroups': group_rows(research['stateGroups'], 'states'),
        'busses': sorted({p for p in bus_paths.values() if p})}


def public(name, e, d) -> dict:
    banks = [d['banks'][k - 1] for k in e['banks']]
    b = banks[0]
    p = b['provider'] or {}
    def label(kind, i):
        row = d[kind].get(i)
        return row['name'] if row and row['name'] else '0x' + i
    return {'name': name, 'family': name.split('/', 1)[0], 'bank': b['name'], 'banks': [x['name'] for x in banks],
        'faction': b['faction'], 'kind': e['kind'], 'rangeM': e.get('range'), 'durationS': e.get('duration'),
        'bus': e.get('bus'), 'globalEffect': ('persistent' if e.get('persistent') else 'transient') if
            e.get('effects') else None, 'effects': e.get('effects', []), 'wwiseName': e.get('wwise'),
        'weapons': e.get('weapons', []), 'stratagem': p.get('stratagem'), 'item': p.get('itemLabel'),
        'residentOnly': not p,
        'parameters': [label('parameters', i) for i in e.get('parameters', [])],
        'volumeParameters': [label('parameters', i) for i in e.get('volume', [])],
        'switchGroups': [label('switchGroups', i) for i in e.get('switchGroups', [])],
        'stateGroups': [label('stateGroups', i) for i in e.get('stateGroups', [])]}


def outputs() -> dict[str, str]:
    d = build()
    catalogue = {'schemaVersion': 1, 'build': d['source']['build'],
        'contract': 'hd2.sounds.list{catalogue = \'events\'} / describe / play (docs/sounds.md); names '
            '<family>/<bank>/<event>: the event\'s Wwise name where the game\'s code or data names it, else its id',
        'summary': d['counts'], 'families': d['families'], 'busses': d['busses'],
        'parameters': [{'name': p['name'] or '0x' + i, 'named': bool(p['name']), 'default': p['default'],
            'events': p['events']} for i, p in d['parameters'].items()],
        'switchGroups': [{'name': g['name'] or '0x' + i, 'values': [v or '0x' + k for k, v in g['values'].items()]}
            for i, g in d['switchGroups'].items()],
        'stateGroups': [{'name': g['name'] or '0x' + i, 'values': [v or '0x' + k for k, v in g['values'].items()]}
            for i, g in d['stateGroups'].items()],
        'events': [public(name, e, d) for name, e in sorted(d['events'].items())]}
    return {LUA_OUTPUT: '-- Generated by scripts/generate_sound_events.py; do not edit.\nreturn ' + lua(d) + '\n',
        JSON_OUTPUT: json.dumps(catalogue, indent=None, separators=(',', ':')).replace('},{"name"', '},\n{"name"')
            + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                with open(path, 'w', encoding='utf-8', newline='') as handle:
                    handle.write(body)
    if check and stale:
        raise RuntimeError('Stale sound event catalogue: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
