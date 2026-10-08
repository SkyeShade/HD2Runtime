"""Underbarrel weapons: the separate weapon entity a host weapon's underbarrel item names. Read-only research.

A host weapon's default underbarrel item (customization slot item whose entity delta writes WeaponCustomization +192,
`underbarrel_path`, name length 16) names an entity resource: the underbarrel weapon, a weapon entity of its own with
its own WeaponData, ProjectileWeapon (or Spray), WeaponRounds and WeaponReload records. At weapon setup the game
resolves that path and creates the underbarrel as a separate game object (game.dll weapon setup 0x74A3D0 -> 0x748F60;
build/scratch/onetwo research). The host keeps its own records; nothing of the underbarrel is on the host entity.

Per underbarrel this records the host(s), the linking item, the entity's weapon components with their record
identities and owner counts, and the values of the members the existing field schema already proves for those
components (schemas/player_weapon_fields.json): WeaponData +84 / +88 (weapon.horizontal_spread / vertical_spread),
WeaponRounds +72 (rounds.feed_capacity_1, live-proven on the SG-20 Halt), +80 (rounds.spare_rounds), +84
(rounds.rounds_from_supply), +88 (rounds.starting_rounds), ProjectileWeapon +8 (weapon.fire_rate) and +0 (the
projectile type). It also lists the player catalog weapons whose runtime roots include an underbarrel entity: those
roots are misattributed (the entity is another weapon's underbarrel), so the catalog must drop them.

Unproven and not published as fields: which of ProjectileWeapon +0 / WeaponRounds +64 the launcher fires from, the
reload time (WeaponReload +56 is 0: the reload ability's own duration applies), WeaponRounds +92 / +104, and whether a
built underbarrel keeps copies of its values (no retained snapshot holds a built one).

Output: research/underbarrel-weapons-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research  # noqa: E402
import research_field_ownership as field_ownership  # noqa: E402
from research_magazine_attachments import DATALIB, DELTAS_SHA, customization_items, entity_deltas, sha  # noqa: E402

OUTPUT = ROOT / 'research/underbarrel-weapons-F5FEE03DCFDB.json'
CATALOG = ROOT / 'schemas/player_weapon_authoring_catalog.json'
FIELDS = ROOT / 'schemas/player_weapon_fields.json'
UNDERBARREL_PATH = 192
# (field, component, offset, storage) the schema proves for these components; checked against the schema below.
MEMBERS = (('weapon.horizontal_spread', 'WeaponDataComponentData', 84, 'f32'),
    ('weapon.vertical_spread', 'WeaponDataComponentData', 88, 'f32'),
    ('weapon.fire_rate', 'ProjectileWeaponComponentData', 8, 'f32'),
    ('rounds.feed_capacity_1', 'WeaponRoundsComponentData', 72, 'f32'),
    ('rounds.spare_rounds', 'WeaponRoundsComponentData', 80, 'u32'),
    ('rounds.rounds_from_supply', 'WeaponRoundsComponentData', 84, 'u32'),
    ('rounds.starting_rounds', 'WeaponRoundsComponentData', 88, 'u32'))


def hx(value, width=16):
    return '0x%0*X' % (width, value)


def main():
    native = entity_research.Native()
    names = field_ownership.component_names(native)
    raw = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(raw) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    deltas, _ = entity_deltas(raw)
    items = customization_items((DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    by_add = {item['addPath']: item for item in items}
    schema = {item['id']: item for item in json.loads(FIELDS.read_text(encoding='utf-8'))['fields']}
    for field, component, offset, storage in MEMBERS:
        if field not in schema:
            raise ValueError('schema lost ' + field)
    owners = native.owners('WeaponCustomizationComponentData')

    def hosts_of(option):
        out = []
        for record, resources in owners.items():
            body = native.record('WeaponCustomizationComponentData', record)
            for at in range(0, 80, 8):
                slot, value = struct.unpack_from('<II', body, at)
                if value == option:
                    out += [{'resource': hx(r), 'slot': slot} for r in resources]
        return out

    def entity(resource):
        report = native.report(hx(resource))
        components = {c['name']: c for c in report['components'] if c.get('resolved') and c.get('name')}
        records = {}
        for name, component in sorted(components.items()):
            if not (name.startswith('Weapon') or name.endswith('WeaponComponentData')):
                continue
            ownership = native.ownership(component)
            records[name] = {'recordIndex': component['record_index'], 'indexRow': component['index_row'],
                'ownerCount': ownership['ownerCount'], 'uniqueOwner': ownership['uniqueOwner']}
        values = {}
        for field, component, offset, storage in MEMBERS:
            if component in components:
                body = native.record(component, components[component]['record_index'])
                value = struct.unpack_from('<f' if storage == 'f32' else '<I', body, offset)[0]
                values[field] = round(value, 6) if storage == 'f32' else value
        projectile = None
        if 'ProjectileWeaponComponentData' in components:
            body = native.record('ProjectileWeaponComponentData',
                components['ProjectileWeaponComponentData']['record_index'])
            projectile = {'projectileWeapon0': struct.unpack_from('<I', body, 0)[0]}
            if 'WeaponRoundsComponentData' in components:
                rounds = native.record('WeaponRoundsComponentData',
                    components['WeaponRoundsComponentData']['record_index'])
                projectile['weaponRounds64'] = struct.unpack_from('<I', rounds, 64)[0]
        reload = None
        if 'WeaponReloadComponentData' in components:
            body = native.record('WeaponReloadComponentData', components['WeaponReloadComponentData']['record_index'])
            reload = {'duration': struct.unpack_from('<f', body, 56)[0],
                'note': 'WeaponReload +56 is 0: the reload ability duration applies; the actual reload time is not '
                    'a component member and stays unpublished'}
        family = next((n.removesuffix('ComponentData') for n in ('ProjectileWeaponComponentData',
            'SprayWeaponComponentData', 'BeamWeaponComponentData', 'ArcWeaponComponentData') if n in components), None)
        return {'resource': hx(resource), 'path': native.path(resource), 'entityRow': native.entity_row(resource),
            'family': family, 'components': records, 'values': values, 'projectile': projectile, 'reload': reload}

    underbarrels = []
    for path, delta in sorted(deltas.items()):
        for entry in delta['entries']:
            if names.get(entry['component']) != 'WeaponCustomizationComponentData':
                continue
            if not (entry['offset'] <= UNDERBARREL_PATH < entry['offset'] + entry['size']):
                continue
            target = struct.unpack_from('<Q', entry['bytes'], UNDERBARREL_PATH - entry['offset'])[0]
            item = by_add.get(path)
            if not item or not target:
                continue
            found = entity(target)
            if not found['family']:
                continue   # a flashlight or other non-weapon underbarrel item
            underbarrels.append({'item': item['debugName'], 'optionId': hx(item['optionId'], 8),
                'addPath': hx(path), 'selfReference': target == path, 'hostsByDefault': hosts_of(item['optionId']),
                'underbarrel': found})
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    ub = {item['underbarrel']['resource'] for item in underbarrels}
    # A corrected weapon (research/weapon-roots) keeps its two candidate roots: the correction is derived from them.
    roots = {w['name']: w.get('candidateRoots') or w['resources'] for w in catalog['weapons']}
    host_names = {r: w['name'] for w in catalog['weapons'] for r in roots[w['name']] if r not in ub}
    corrections = []
    for item in underbarrels:
        item['hosts'] = sorted({host_names[h['resource']] for h in item['hostsByDefault']
            if h['resource'] in host_names})
        resource = item['underbarrel']['resource']
        for weapon in catalog['weapons']:
            candidates = roots[weapon['name']]
            if resource in candidates and len(candidates) > 1:
                kept = [r for r in candidates if r != resource]
                corrections.append({'weapon': weapon['name'], 'dropRoot': resource, 'underbarrelOf': item['hosts'],
                    'keptRoots': kept, 'resolution': 'UNIQUE' if len(kept) == 1 else weapon['resolution']})
    result = {'schemaVersion': 1, 'mode': 'offline', 'writes': 0,
        'model': ('An underbarrel is a separate weapon entity named by the host\'s default underbarrel item (its delta '
            'sets WeaponCustomization +192 underbarrel_path to the entity); the host entity carries none of its '
            'records.'),
        'members': [{'field': f, 'component': c, 'offset': o, 'storage': s} for f, c, o, s in MEMBERS],
        'unproven': ['which of ProjectileWeapon +0 / WeaponRounds +64 the underbarrel fires from',
            'the reload time (the reload ability duration)', 'WeaponRounds +92 and +104',
            'whether a built underbarrel keeps copies of its values'],
        'underbarrels': underbarrels, 'catalogCorrections': corrections}
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'underbarrels': [(u['hosts'], u['underbarrel']['resource'], u['underbarrel']['family'])
        for u in underbarrels], 'corrections': corrections}, indent=1))


if __name__ == '__main__':
    main()
