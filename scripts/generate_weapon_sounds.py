"""Generate the weapon firing-sound catalogue from research/weapon-sounds-F5FEE03DCFDB.json
(docs/research/weapon-sounds-F5FEE03DCFDB.md; docs/weapon-sounds.md):

- domains/weapon_sounds.lua: the Runtime's catalogue (runtime/weapon_sounds.lua): every entry by its semantic name
  `<family>/<weapon>[/<part>]`, its events (kept here for the Runtime only), its bank, the packages that list the bank,
  the stratagem whose call-in package provides it (or resident-only), the writes a Pelican chin-turret copy takes, the
  aliases and the pins the sound path re-proves;
- sdk/WeaponSoundCatalogue.json: the same catalogue for ModBuilder and mod authors, without any raw id.

The names are assigned here from the repo's catalogues (reviewed tables below for vehicles, sentries, emplacements and
Eagles; designations for support, primary and secondary weapons; the Filediver path or the bank for the rest). A type
whose sound is the same as a higher-priority entry's (same events) and that names no other catalogued weapon is folded
into that entry (its resource counted in `also`).
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/weapon-sounds-F5FEE03DCFDB.json'
LUA_OUTPUT = 'domains/weapon_sounds.lua'
JSON_OUTPUT = 'sdk/WeaponSoundCatalogue.json'
# Older names kept working (r7: the reviewed allowlist's only sound).
ALIASES = {'maelstrom_main_gun': 'vehicle/maelstrom/main_gun'}
# How many packages an entry's residency check reads (the requested call-in packages first, then the smallest).
MAX_PACKAGES = 12
NOT_MISSION_PACKAGES = ('packages/content/audio_test_level',)
PELICAN = 'pelican/chin_autocannon'
# Reviewed vehicle mount names: (vehicle, mount slot) -> (name, label).
VEHICLES = {
    ('M-103 Supply FRV', 0): ('vehicle/supply_frv/gun', 'M-103 Supply FRV gun'),
    ('TD-110 Maelstrom', 0): ('vehicle/maelstrom/main_gun', 'TD-110 Maelstrom main gun'),
    ('TD-110 Maelstrom', 2): ('vehicle/maelstrom/slot_2', 'TD-110 Maelstrom slot 2 weapon'),
    ('TD-110 Maelstrom', 3): ('vehicle/maelstrom/rockets', 'TD-110 Maelstrom rockets'),
    ('TD-110 Maelstrom', 4): ('vehicle/maelstrom/rockets', 'TD-110 Maelstrom rockets'),
    ('M-104 Incinerator FRV', 0): ('vehicle/incinerator_frv/flamethrower', 'M-104 Incinerator FRV flamethrower'),
    ('EXO-49 Emancipator Exosuit', 0): ('vehicle/emancipator/autocannons', 'EXO-49 Emancipator Exosuit autocannons'),
    ('EXO-49 Emancipator Exosuit', 1): ('vehicle/emancipator/autocannons', 'EXO-49 Emancipator Exosuit autocannons'),
    ('EXO-45 Patriot Exosuit', 0): ('vehicle/patriot/rockets', 'EXO-45 Patriot Exosuit rocket launcher'),
    ('EXO-45 Patriot Exosuit', 1): ('vehicle/patriot/minigun', 'EXO-45 Patriot Exosuit minigun'),
    ('M-102 Gunner FRV', 0): ('vehicle/gunner_frv/hmg', 'M-102 Gunner FRV heavy machine gun'),
    ('FRV (Super Earth variant)', 0): ('vehicle/gunner_frv/hmg', 'M-102 Gunner FRV heavy machine gun'),
    ('TD-220 Bastion MK XVI', 0): ('vehicle/bastion/cannon', 'TD-220 Bastion MK XVI cannon'),
    ('TD-220 Bastion MK XVI', 1): ('vehicle/bastion/hmg', 'TD-220 Bastion MK XVI heavy machine gun'),
    ('EXO-55 Breakthrough Exosuit', 1): ('vehicle/breakthrough/flak_cannon', 'EXO-55 Breakthrough Exosuit flak cannon'),
    ('EXO-51 Lumberer Exosuit', 0): ('vehicle/lumberer/flamethrower', 'EXO-51 Lumberer Exosuit flamethrower'),
    ('EXO-51 Lumberer Exosuit', 1): ('vehicle/lumberer/cannon', 'EXO-51 Lumberer Exosuit anti-tank cannon'),
    ('GATER Oil Rig', 0): ('vehicle/oil_rig/turret', 'GATER Oil Rig turret'),
    ('AX/AR-23 Guard Dog', 0): ('backpack/guard_dog', 'AX/AR-23 Guard Dog'),
    ('AX/LAS-5 Rover', 0): ('backpack/rover', 'AX/LAS-5 Rover'),
    ('AX/FLAM-75 Hot Dog', 0): ('backpack/hot_dog', 'AX/FLAM-75 Hot Dog'),
    ('AX/ARC-3 K-9', 0): ('backpack/k9', 'AX/ARC-3 K-9'),
    ('AX/TX-13 Dog Breath', 0): ('backpack/dog_breath', 'AX/TX-13 Dog Breath'),
}
# Reviewed stratagem payload names (sentries, emplacements; every Eagle shares one cannon).
STRATAGEMS = {
    'A/MG-43 Machine Gun Sentry': 'sentry/machine_gun', 'A/G-16 Gatling Sentry': 'sentry/gatling',
    'A/AC-8 Autocannon Sentry': 'sentry/autocannon', 'A/M-12 Mortar Sentry': 'sentry/mortar',
    'A/MLS-4X Rocket Sentry': 'sentry/rocket', 'A/M-23 EMS Mortar Sentry': 'sentry/ems_mortar',
    'A/GM-17 Gas Mortar Sentry': 'sentry/gas_mortar', 'A/LAS-98 Laser Sentry': 'sentry/laser',
    'A/FLAM-40 Flame Sentry': 'sentry/flame', 'A/ARC-3 Tesla Tower': 'sentry/tesla',
    'E/MG-101 HMG Emplacement': 'emplacement/hmg', 'E/AT-12 Anti-Tank Emplacement': 'emplacement/anti_tank',
    'E/GL-21 Grenadier Battlement': 'emplacement/grenadier',
}
EAGLE = ('eagle/cannon', 'Eagle cannon (strafing run)')
# A part for a named weapon's other sound: SEAF troopers' versions live in their own bank.
SEAF_BANK = 'content/audio/foley_seafs'
# Unnamed entries: the family from the bank's prefix.
BANK_FAMILIES = (('bots_', 'automaton'), ('cyborg_', 'automaton'), ('weapons_bots', 'automaton'),
    ('env_bots', 'automaton'), ('illuminates_', 'illuminate'), ('bugs_', 'terminid'), ('foley_seafs', 'seaf'),
    ('obj_', 'objective'))
FAMILY_LABELS = {'automaton': 'Automaton', 'illuminate': 'Illuminate', 'terminid': 'Terminid', 'objective': 'Objective',
    'other': 'Other', 'seaf': 'SEAF'}


def designation(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.split(' ')[0].lower())


def sound_key(e):
    s = e['sound']
    return (s['kind'], s['start'], s['stop']) if s['kind'] == 'loop' else (s['kind'], s['event'], s['midi'])


def candidate(e):
    """The best name source of one research entry: (priority, weapon key, name, label, family)."""
    by = collections.defaultdict(list)
    for s in e['sources']:
        by[s['catalogue']].append(s)
    if by['pelican']:
        return (0, PELICAN, PELICAN, 'Pelican chin autocannon (its own sound)')
    for s in by['vehicle']:
        name, label = VEHICLES[(s['vehicle'], s['slot'])]
        return (1, name, name, label)
    for s in by['stratagem']:
        if s['family'] == 'eagle':
            return (2, EAGLE[0], EAGLE[0], EAGLE[1])
        if s['stratagem'] in STRATAGEMS:
            return (2, STRATAGEMS[s['stratagem']], STRATAGEMS[s['stratagem']], s['stratagem'])
    for s in by['support']:
        name = 'support/' + designation(s['weapon'])
        return (3, name, name, s['weapon'])
    for s in by['player']:
        name = s['slot'] + '/' + designation(s['weapon'])
        return (4, name, name, s['weapon'])
    path = e['path']
    if path:
        parts = path.split('/')
        base = parts[-1]
        family = {'fac_cyborgs': 'automaton', 'fac_illuminate': 'illuminate', 'fac_bugs': 'terminid',
            'objectives': 'objective'}.get(parts[1], 'other')
        if family == 'automaton' and base.startswith('cyborg_'):
            base = base[len('cyborg_'):]
        name = family + '/' + base
        return (5, name, name, '%s %s' % (FAMILY_LABELS[family], base.replace('_', ' ')))
    return (6, None, None, None)


def bank_unit(bank: str):
    short = bank.rsplit('/', 1)[-1]
    for prefix, family in BANK_FAMILIES:
        if short.startswith(prefix):
            return family, short[len(prefix):] if prefix.endswith('_') else ''
    return 'other', short


def build() -> dict:
    return catalogue()[0]


def names_by_resource() -> dict[str, str]:
    """Every sounding ProjectileWeapon type (by resource) -> the catalogue name of its sound (a folded type's is the
    entry it was folded into): the sound a weapon type makes as built, for the weapon.sound field."""
    return catalogue()[1]


def catalogue():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges']:
        raise ValueError('the weapon sound research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned sound instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the weapon sound research covers another build than schemas/current.lua')
    for (vehicle, slot) in {(s['vehicle'], s['slot']) for e in research['entries'] for s in e['sources']
            if s['catalogue'] == 'vehicle'}:
        if (vehicle, slot) not in VEHICLES:
            raise ValueError('a sounding vehicle mount has no reviewed name: %s slot %d' % (vehicle, slot))
    stratagems = research['stratagems']
    if any(p['residentInSnapshots'] for p in research['packages'].values() if p['name'] in NOT_MISSION_PACKAGES):
        raise ValueError('a package taken for no mission package was resident in a retained snapshot')
    rows = []
    for e in research['entries']:
        priority, weapon, name, label = candidate(e)
        rows.append({'e': e, 'priority': priority, 'weapon': weapon, 'name': name, 'label': label, 'key': sound_key(e),
            'bank': e['banks'][0]['name'], 'folded': [], 'into': None})

    # 1. One named weapon: its sounds (the first by preference keeps the name; SEAF troopers' and other sounds get a
    #    part); the same sound of the same weapon is folded.
    def preference(r):
        return (r['bank'] == SEAF_BANK, r['e']['path'] is None, r['e']['resource'])
    groups = collections.defaultdict(list)
    for r in rows:
        if r['weapon']:
            groups[r['weapon']].append(r)
    for weapon, members in groups.items():
        members.sort(key=preference)
        keys = {}
        alt = 0
        for r in members:
            if r['key'] in keys:
                r['into'] = keys[r['key']]
                continue
            keys[r['key']] = r
            if r is members[0]:
                continue
            if r['bank'] == SEAF_BANK:
                r['name'], r['label'] = r['name'] + '/seaf', r['label'] + ' (SEAF trooper)'
            else:
                alt += 1
                r['name'], r['label'] = r['name'] + '/alt' + (str(alt) if alt > 1 else ''), r['label'] + ' (alternate)'
    # 2. A sound already catalogued under a reviewed or catalogued name: the path- or bank-named types fold into it.
    named = collections.defaultdict(list)
    for r in rows:
        if r['into'] is None and r['priority'] <= 4:
            named[r['key']].append(r)
    for r in rows:
        if r['into'] is None and r['priority'] >= 5 and named.get(r['key']):
            r['into'] = sorted(named[r['key']], key=lambda t: (t['priority'], t['name']))[0]
    # 3. Path-named types with the same sound: the first by name keeps it.
    pathed = collections.defaultdict(list)
    for r in rows:
        if r['into'] is None and r['priority'] == 5:
            pathed[r['key']].append(r)
    for members in pathed.values():
        members.sort(key=lambda t: (len(t['name']), t['name']))
        for r in members[1:]:
            r['into'] = members[0]
    # 4. Unidentified types (no catalogue name, no path): by the bank's family and unit, numbered by resource; the
    #    same sound folds into a path-named one first, else the first of them.
    for r in rows:
        if r['into'] is None and r['priority'] == 6:
            same = [t for t in rows if t['into'] is None and t['priority'] == 5 and t['key'] == r['key']]
            if same:
                r['into'] = sorted(same, key=lambda t: (len(t['name']), t['name']))[0]
    unnamed = collections.defaultdict(list)
    for r in rows:
        if r['into'] is None and r['priority'] == 6:
            unnamed[r['key']].append(r)
    keepers = []
    for members in unnamed.values():
        members.sort(key=lambda t: t['e']['resource'])
        for r in members[1:]:
            r['into'] = members[0]
        keepers.append(members[0])
    units = collections.defaultdict(list)
    for r in keepers:
        units[bank_unit(r['bank'])].append(r)
    for (family, unit), members in units.items():
        members.sort(key=lambda t: t['e']['resource'])
        for k, r in enumerate(members, 1):
            r['name'] = '/'.join(p for p in (family, unit, str(k)) if p)
            r['label'] = '%s %sweapon %d (unidentified; bank %s)' % (FAMILY_LABELS[family], unit.replace('_', ' ')
                + ' ' if unit else '', k, r['bank'].rsplit('/', 1)[-1])
    for r in rows:
        while r['into'] is not None and r['into']['into'] is not None:
            r['into'] = r['into']['into']
        if r['into'] is not None:
            r['into']['folded'].append(r['e']['resource'])

    sounds = {}
    for r in rows:
        if r['into'] is not None:
            continue
        e, s = r['e'], r['e']['sound']
        if r['name'] in sounds:
            raise ValueError('two catalogue entries are named ' + r['name'])
        own = r['name'] == PELICAN or not (e['chin']['writes'] or e['chin']['instanceWrites'])
        # The stratagem whose call-in package provides one of its banks: the smallest such (complete) call-in.
        options = sorted((c for c in e['stratagems'] if c['complete']), key=lambda c: (c['bytes'], c['name']))
        stratagem = None if own or not options else options[0]['name']
        # The call-in packages the Runtime requests: those of the stratagem that list one of its banks.
        banks = {b['resource'] for b in e['banks']}
        requests = [p['package'] for p in stratagems[stratagem]['packages'] if set(p['banks']) & banks] \
            if stratagem else []
        if stratagem and not requests:
            raise ValueError(r['name'] + ': its stratagem lists none of its banks')
        provided = {b for p in stratagems[stratagem]['packages'] for b in p['banks']} if stratagem else set()
        if r['name'] == PELICAN:   # the Pelican's own bank (its sound is also in two others)
            provided = {b['resource'] for b in e['banks'] if b['name'] == 'content/audio/vehicle_shuttle'}
        bank = next((b for b in e['banks'] if b['resource'] in provided), e['banks'][0])
        # The residency check reads the requested packages first, then the smallest others that list a bank (never the
        # audio test level's package, which lists every bank and no retained snapshot had resident).
        info = research['packages']
        package_list = list(requests) + [p for p in e['packages'] if p not in requests
            and info[p]['name'] not in NOT_MISSION_PACKAGES]
        package_list = package_list[:max(MAX_PACKAGES, len(requests))]

        def label_of(p):
            name = info[p]['name'] if p in info else None
            return name or ('call-in package of ' + stratagem if p in requests else 'package ' + p)
        rng = e['range']
        entry = {'label': r['label'], 'family': r['name'].split('/')[0], 'resource': e['resource'], 'kind': s['kind'],
            'fireMode': e['fireMode'], 'rpm': e['rpmSlots'][1],
            'bank': {'name': bank['name'], 'resource': bank['resource']},
            'banks': [b['name'] for b in e['banks']],
            'packages': [{'package': p, 'label': label_of(p)} for p in package_list],
            'residentOnly': stratagem is None and not own, 'own': own,
            'range': {'heuristic': True, 'maxDistance': rng['maxDistance'], 'layers': rng['layers']} if rng else None,
            'writes': e['chin']['writes'], 'instanceWrites': e['chin']['instanceWrites'],
            'blockBytes': chin_block(research, e['chin']['writes']),
            'also': len(r['folded'])}
        if s['kind'] == 'loop':
            entry.update({'start': s['start'], 'stop': s['stop'], 'midi': 0})
        else:
            entry.update({'event': s['event'], 'midi': s['midi']})
        if stratagem:
            entry.update({'stratagem': stratagem, 'stratagemId': stratagems[stratagem]['stableId'],
                'requests': requests})
        sil = e['silenced']
        if sil['silenced'] or any(sil[k] != '00000000' for k in ('silencedLoopStart', 'silencedLoopStop',
                'silencedSingle')):
            entry['silenced'] = {'flag': sil['silenced'], 'loopStart': sil['silencedLoopStart'],
                'loopStop': sil['silencedLoopStop'], 'single': sil['silencedSingle']}
        sounds[r['name']] = entry
    for alias, target in ALIASES.items():
        if target not in sounds or alias in sounds:
            raise ValueError('alias %s -> %s' % (alias, target))
    unique = {}
    for group in research['pins'].values():
        for pin in group:
            unique.setdefault(pin['rva'], {'label': pin['role'], 'rva': pin['rva'], 'hex': pin['bytes']})
    folded = sum(len(r['folded']) for r in rows if r['into'] is None)
    by_resource = {r['e']['resource']: (r['into'] or r)['name'] for r in rows}
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256']},
        'chin': research['chin'], 'record': {k: research['record'][k] for k in ('stride', 'blocks', 'span')},
        'instance': research['instance'],
        'counts': {'types': research['counts']['types'], 'sounding': research['counts']['sounding'],
            'entries': len(sounds), 'folded': folded, 'notCatalogued': research['counts']['notCatalogued']},
        'aliases': ALIASES, 'sounds': dict(sorted(sounds.items())),
        'pins': sorted(unique.values(), key=lambda pin: pin['rva'])}, by_resource


def chin_block(research, writes) -> str:
    """The chin turret's firing-sound block after the writes (what its copy reads back)."""
    raw = bytearray(bytes.fromhex(research['chin']['blockBytes']))
    position, at = {}, 0
    for offset, size in research['record']['blocks']:
        for k in range(size):
            position[offset + k] = at + k
        at += size
    for w in writes:
        for k, byte in enumerate(bytes.fromhex(w['to'])):
            raw[position[w['offset'] + k]] = byte
    return raw.hex()


def public(name, s) -> dict:
    """An entry as mods see it: no event, bank or package id."""
    out = {'name': name, 'label': s['label'], 'family': s['family'], 'kind': s['kind'],
        'stratagem': s.get('stratagem'), 'residentOnly': s['residentOnly'], 'pelicanDefault': s['own'],
        'midi': bool(s['midi']), 'designedRpm': s['rpm'], 'fireMode': s['fireMode'],
        'rangeM': s['range']['maxDistance'] if s['range'] else None,
        'layers': s['range']['layers'] if s['range'] else [], 'bank': s['bank']['name'], 'alsoTypes': s['also']}
    return out


def outputs() -> dict[str, str]:
    d = build()
    families = collections.Counter(s['family'] for s in d['sounds'].values())
    catalogue = {'schemaVersion': 1, 'build': d['source']['build'],
        'contract': 'hd2.sounds.list / describe (docs/weapon-sounds.md); a name of kind shot or loop is accepted by '
            'hd2.pelican.spawn{gun = {sound = name}} and a custom stratagem\'s pelican.gun.sound',
        'summary': {**{k: d['counts'][k] for k in ('types', 'sounding', 'entries', 'folded')},
            'byFamily': dict(sorted(families.items())),
            'byKind': dict(sorted(collections.Counter(s['kind'] for s in d['sounds'].values()).items())),
            'withStratagem': sum(1 for s in d['sounds'].values() if s.get('stratagem')),
            'residentOnly': sum(1 for s in d['sounds'].values() if s['residentOnly'])},
        'rangeIsHeuristic': True, 'aliases': d['aliases'],
        'sounds': [public(name, s) for name, s in d['sounds'].items()]}
    return {LUA_OUTPUT: '-- Generated by scripts/generate_weapon_sounds.py; do not edit.\nreturn ' + lua(d) + '\n',
        JSON_OUTPUT: json.dumps(catalogue, indent=1) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale weapon sound catalogue: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
