"""More projectile donors for the projectile-reference swap (docs/attack-outputs.md, "More donors"), read-only, from
research/projectile-identities-F5FEE03DCFDB.json and the retained snapshot.

The swap's donor pool is the attack-output catalogue (hd2.attack_output(name)): a donor is a projectile type held by
one typed member of one uniquely owned component record, whose live value the write re-proves before every write,
with a package the Runtime can load first. The identity research named 224 of 350 projectile types; 81 of them are
already catalogued outputs. This research takes every other named type whose owner is one of:

  * a stratagem's Eagle payload (EagleComponentData +24), orbital shell (BombardmentComponentData +64), orbital
    ability projectile (OrbitalAbilityComponentData +532), or a stratagem entity's own ProjectileWeapon +0 (sentries,
    emplacements);
  * a catalogued player or support weapon's other ProjectileWeapon member (+576, the weapon's second projectile) or
    its own +0 when it is not catalogued yet;
  * a catalogued vehicle's mounted weapon;

with exactly one owner record (the record's own member holds the type in the snapshot), and classifies its row with
the swap's own rule (research_attack_outputs.projectile_class). Enemy weapons (their effects ship in faction
packages), unnamed owners, guided-missile components and array members (magazine round patterns, charge, heat and
rounds levels: their element strides are not proven here) are left out, each with the reason.

Output: research/projectile-donors-F5FEE03DCFDB.json.  py scripts/research_projectile_donors.py [--check]
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
sys.path.insert(0, str(ROOT / 'sdk'))
import build_profile  # noqa: E402
import research_attack_outputs as attack_outputs  # noqa: E402
import research_throwable_authoring as throwables  # noqa: E402
import research_weapon_fire_modes as fire_modes  # noqa: E402

OUTPUT = ROOT / 'research/projectile-donors-F5FEE03DCFDB.json'
IDENTITIES = ROOT / 'research/projectile-identities-F5FEE03DCFDB.json'
CATALOGUED = ROOT / 'research/attack-outputs-F5FEE03DCFDB.json'
STUN = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
STRATAGEMS = ROOT / 'sdk/StratagemAuthoringCapabilities.json'
PLAYER = ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json'
SUPPORT = ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json'
VEHICLES = ROOT / 'sdk/VehicleWeaponCapabilities.json'
# (component, member) -> the owner kind a donor of it has.
MEMBERS = {
    ('EagleComponentData', 24): 'stratagem',
    ('BombardmentComponentData', 64): 'stratagem',
    ('OrbitalAbilityComponentData', 532): 'stratagem',
    ('ProjectileWeaponComponentData', 0): None,      # by the owner's name: a weapon, a stratagem entity or a mount
    ('ProjectileWeaponComponentData', 576): None,
}
ROLE = {('EagleComponentData', 24): 'Eagle payload', ('BombardmentComponentData', 64): 'orbital shell',
    ('OrbitalAbilityComponentData', 532): 'orbital projectile', ('ProjectileWeaponComponentData', 0): 'fired projectile',
    ('ProjectileWeaponComponentData', 576): 'second projectile (+576)'}
# The profile must describe the owner component, or the source cannot be re-proven live.
PROFILE = ROOT / 'schemas/current.lua'


def names_of(path, key='weapons'):
    data = json.loads(path.read_text(encoding='utf-8'))
    items = data.get(key) or []
    if isinstance(items, dict):
        return set(items)
    return {i['name'] if isinstance(i, dict) else i for i in items}


def build():
    identities = json.loads(IDENTITIES.read_text(encoding='utf-8'))
    catalogued = {w['output']['type'] for w in json.loads(CATALOGUED.read_text(encoding='utf-8'))['weapons']
        if w.get('family') == 'projectile' and w.get('output')}
    # The stun-field donors (research/stun-field-donors) are catalogued already, for their own field scope.
    catalogued |= {d['projectileType'] for d in json.loads(STUN.read_text(encoding='utf-8'))['donors']}
    stratagems = names_of(STRATAGEMS, 'stratagems')
    players = names_of(PLAYER)
    supports = names_of(SUPPORT)
    profile = PROFILE.read_text(encoding='utf-8')
    profiled = set(re.findall(r'\["(\w+ComponentData)"\]=\{\["offset"\]', profile))
    native = throwables.Native()
    view = native.view
    rows_native = fire_modes.entity_research.Native()

    def owner_kind(component, member, names):
        fixed = MEMBERS[(component, member)]
        if fixed:
            name = next((n for n in names if n in stratagems), None)
            return (fixed, name) if name else (None, None)
        for n in names:
            if n in players:
                return 'player_weapon', n
            if n in supports:
                return 'support_weapon', n
            if n in stratagems:
                return 'stratagem', n
        return None, None

    donors, refused = [], []
    candidates = []
    for t in identities['types']:
        if not t.get('runtimeName') or t['type'] in catalogued:
            continue
        candidates.append(t)
    for t in candidates:
        verdict = None
        enemy = any('enemy' in n['category'] for o in t['identity']['owners'] for n in o['names'])
        for o in t['identity']['owners']:
            try:
                member = int(o['member'])
            except ValueError:
                continue    # an array element: not a single fixed member
            key = (o['component'], member)
            if key not in MEMBERS or o.get('recordShared'):
                continue
            names = [n['name'] for n in o['names'] if 'enemy' not in n['category']]
            kind, name = owner_kind(o['component'], member, names)
            if not kind:
                continue
            if o['component'] not in profiled:
                verdict = verdict or ('refused', o['component'] + ' is not in the runtime profile')
                continue
            resource = int(o['resource'], 16)
            record = view.record(o['component'], resource)
            if not record or record['ownerCount'] != 1:
                verdict = verdict or ('refused', 'the owner record is not uniquely owned')
                continue
            value = struct.unpack_from('<I', record['bytes'], member)[0]
            if value != t['type']:
                verdict = verdict or ('refused', 'the owner member holds %d, not %d' % (value, t['type']))
                continue
            verdict = ('donor', {'ownerKind': kind, 'owner': name, 'role': ROLE[key], 'component': o['component'],
                'member': member, 'resource': o['resource'], 'path': o.get('path'),
                'entityRow': rows_native.entity_row(resource),
                'componentIdentity': {'recordIndex': record['recordIndex'], 'indexRow': record['indexRow'],
                    'ownerCount': record['ownerCount'], 'uniqueOwner': True}})
            break
        if verdict and verdict[0] == 'donor':
            donors.append(dict(verdict[1], projectileType=t['type'], runtimeName=t['runtimeName'],
                properties=t['properties']))
        else:
            reason = (verdict[1] if verdict else 'its owner is an enemy weapon (faction packages)' if enemy else
                'no single fixed member of a named, uniquely owned record holds it (array members, unnamed owners, '
                'guided missiles and objective shells are not donors here)')
            refused.append({'projectileType': t['type'], 'runtimeName': t['runtimeName'], 'reason': reason})
    settings = attack_outputs.resolve_settings(sorted(d['projectileType'] for d in donors), [], [])
    for d in donors:
        row = settings['projectiles'].get(str(d['projectileType']))
        if not row:
            raise ValueError('no projectile row for type %d' % d['projectileType'])
        d['settings'] = row['settings']
        d['velocity'], d['mass'], d['damage'] = row['velocity'], row['mass'], row['damage']
        d['impact'], d['expiry'] = row.get('impact'), row.get('expiry')
        d['compatibilityClass'] = attack_outputs.projectile_class(row)
    # Names: '<owner> (projectile <type>)' always; '<owner>' alone when the owner has exactly one donor here and is
    # not a weapon (a weapon's own name already names its catalogued output).
    per_owner = {}
    for d in donors:
        per_owner.setdefault(d['owner'], []).append(d)
    for d in donors:
        d['name'] = '%s (projectile %d)' % (d['owner'], d['projectileType'])
        d['aliases'] = [d['name']] + ([d['owner']] if len(per_owner[d['owner']]) == 1
            and d['ownerKind'] == 'stratagem' else [])
    donors.sort(key=lambda d: (d['ownerKind'], d['owner'], d['projectileType']))
    refused.sort(key=lambda r: r['projectileType'])
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'snapshot': build_profile.SNAPSHOT_NAME,
        'question': 'Which named projectile types can be projectile-reference donors (hd2.attack_output) without new '
            'native research?',
        'rule': 'one fixed member of one uniquely owned, profiled component record holds the type (re-proven live '
            'before every write); a catalogued owner whose package the Runtime can load; the swap class rule',
        'donors': donors, 'refused': refused,
        'summary': {'named': sum(1 for t in identities['types'] if t.get('runtimeName')),
            'alreadyCatalogued': len(catalogued), 'candidates': len(candidates),
            'donors': len(donors), 'refused': len(refused),
            'byOwnerKind': {k: sum(d['ownerKind'] == k for d in donors) for k in sorted({d['ownerKind'] for d in donors})},
            'byClass': {k: sum(d['compatibilityClass'] == k for d in donors)
                for k in sorted({d['compatibilityClass'] for d in donors})}},
        'writes': 0, 'protectionChanges': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    body = json.dumps(build(), indent=1) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != body:
            raise SystemExit('stale: ' + OUTPUT.relative_to(ROOT).as_posix())
        print('up to date')
        return
    OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    print(json.dumps(json.loads(body)['summary'], indent=1))


if __name__ == '__main__':
    main()
