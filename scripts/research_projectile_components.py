"""The projectile component catalogue: every vanilla projectile row split into the hybrid-row components of
domains/projectile_rows.lua (docs/custom-projectile-rows.md). Read-only.

For each of the 350 vanilla ProjectileSettings rows (the pinned datalibrary, compared byte for byte with the live rows
of a retained mission snapshot) it records:

* identity: the catalogued attack outputs that fire the type (domains/attack_outputs.lua; an established output with a
  known package can be a custom projectile donor) and the hd2.projectiles weapon catalogue (domains/event_natives.lua);
* whether the row has a unit (+0x80): the visible part of a unit projectile is its unit, a LATE_LOOKUP member, so only
  unit-less rows can give their visual to a unit-less base such as the LAS-58 Talon;
* each component's values, exactly the members the component descriptor owns: ProjectileVisual (the spawn particle
  effects), ProjectileDamage (the direct-hit DamageInfo, decoded from the damage table), ProjectileImpactExplosion
  (decoded from the explosion table) and ProjectileBallistics (diameter, speed, mass, drag, gravity, lifetime variance,
  penetration slowdown);
* the asset packages a donor needs, resolved like the runtime does (the output's dependencyKey in
  domains/package_residency.lua).

Identical component values are grouped. Output: research/projectile-components-F5FEE03DCFDB.json; the human-readable
report is generated from it by scripts/generate_projectile_catalogue_report.py.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_projectile_builder as builder  # noqa: E402
from lua_offline import execute  # noqa: E402

OUTPUT = ROOT / 'research/projectile-components-F5FEE03DCFDB.json'
SNAPSHOT = 'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap'
STATUSES = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
TEMPLATES = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
TABLE, ROW, TYPES = 0x37C7670, 272, 351
UNIT = 0x80


def lua_domains() -> dict:
    """The runtime's own data: component descriptors, projectile outputs, the weapon projectile catalogue and the
    package database, read by the offline Lua VM from the generated domain files."""
    parts = []
    for name in ('projectile_rows', 'attack_outputs', 'event_natives', 'package_residency'):
        parts.append('local %s=(function()\n%s\nend)()\n' % (name, (ROOT / 'domains' / (name + '.lua')).read_text(
            encoding='utf-8')))
    parts.append('local json=(function()\n%s\nend)()\n' % (ROOT / 'primary_mapper/json.lua').read_text(encoding='utf-8'))
    parts.append(r'''
local outputs={}
for id,o in pairs(attack_outputs.outputs)do
 if o.family=='projectile'then
  local dependency=o.dependencyKey and package_residency.dependencies[o.dependencyKey]
  local package=dependency and package_residency.packages[dependency.package]
  outputs[#outputs+1]={id=id,kind=o.owner and o.owner.kind,name=o.owner and o.owner.name,type=o.currentDefault,
   spare=o.spare~=nil,dependencyKey=o.dependencyKey,package=dependency and dependency.package,
   packageName=package and package.name,packageKnown=package~=nil and package.inBundleDatabase==true}
 end
end
return json.encode({components=projectile_rows.components,members=projectile_rows.members,outputs=outputs,
 weapons=event_natives.projectile.types})''')
    return json.loads(execute(''.join(parts).encode()))


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 5)


def hex64(raw, at):
    return '0x%016X' % struct.unpack_from('<Q', raw, at)[0]


def main():
    domains = lua_domains()
    components = {c['id']: c for c in domains['components']}
    projectiles = builder.settings_rows('generated_projectile_settings.dl_bin', 'ProjectileSettings', ROW)
    explosions = builder.settings_rows('generated_explosion_settings.dl_bin', 'ExplosionSettings', 152)
    damages = builder.settings_rows('generated_damage_settings.dl_bin', 'DamageSettings', 76)
    status_name = {row['nativeType']: row['semanticId'] for row in
        json.loads(STATUSES.read_text(encoding='utf-8'))['statuses']}
    templates = json.loads(TEMPLATES.read_text(encoding='utf-8'))['templates']
    if sorted(projectiles) != list(range(1, TYPES)):
        raise ValueError('the datalibrary does not hold exactly the vanilla types 1..350')

    # The live table of a retained mission snapshot must hold exactly these rows.
    mem = base.Mem(SNAPSHOT)
    live = {}
    for kind in range(1, TYPES):
        record = mem.ptr(mem.game + TABLE + 8 * kind)
        live[kind] = record and mem.read(record, ROW)
    mem.close()
    mismatched = [kind for kind in range(1, TYPES) if live[kind] != projectiles[kind]['bytes']]

    def damage_view(kind):
        item = damages.get(kind)
        if not kind or not item:
            return None
        raw = item['bytes']
        return {'type': kind, 'standard': struct.unpack_from('<i', raw, 4)[0],
            'durable': struct.unpack_from('<i', raw, 8)[0], 'armorPenetration': list(struct.unpack_from('<4I', raw, 12)),
            'statuses': [{'status': status_name.get(u32(raw, 44 + 8 * i), u32(raw, 44 + 8 * i)),
                'strength': f32(raw, 48 + 8 * i)} for i in range(4) if u32(raw, 44 + 8 * i)]}

    def explosion_view(kind):
        item = explosions.get(kind)
        if not kind or not item:
            return None
        raw = item['bytes']
        volume = u32(raw, 100)
        return {'type': kind, 'damage': damage_view(u32(raw, 4)), 'radii': [f32(raw, 16), f32(raw, 20), f32(raw, 24)],
            'volume': templates.get(str(volume), volume) if volume else None,
            'volumeSeconds': f32(raw, 104) if volume else None, 'submunition': u32(raw, 84) or None,
            'arc': u32(raw, 120) or None}

    def values(component, raw):
        out = {}
        for member in component['members']:
            at, label = member['offset'], member['label']
            if member['width'] == 8:
                out[label] = hex64(raw, at)
            elif label in ('direct_damage', 'impact_explosion'):
                out[label] = u32(raw, at)
            else:
                out[label] = f32(raw, at)
        return out

    def key(component, raw):
        return ''.join(raw[m['offset']:m['offset'] + m['width']].hex() for m in component['members'])

    identities = {}
    for output in domains['outputs']:
        if output.get('type'):
            donor = not output['spare'] and output['packageKnown']
            identities.setdefault(output['type'], []).append({'kind': 'output', 'output': output['id'],
                'owner': output['kind'], 'name': output['name'], 'runtimeDonor': donor,
                'package': output['package'] if output['packageKnown'] else None,
                'packageName': output['packageName'] if output['packageKnown'] else None})
    for weapon in domains['weapons']:
        identities.setdefault(weapon['type'], []).append({'kind': 'weapon_projectile', 'name': weapon['weapon'],
            'role': weapon['role']})

    rows, groups = [], {cid: {} for cid in components}
    for kind in range(1, TYPES):
        raw = projectiles[kind]['bytes']
        who = identities.get(kind, [])
        donors = sorted({i['name'] for i in who if i.get('runtimeDonor')})
        packages = sorted({(i['package'], i['packageName']) for i in who if i.get('package')})
        row = {'type': kind, 'row': projectiles[kind]['row'], 'identities': who, 'runtimeDonors': donors,
            'packages': [{'package': p, 'name': n} for p, n in packages], 'unit': u32(raw, UNIT) != 0 or
            u32(raw, UNIT + 4) != 0, 'components': {}}
        for cid, component in components.items():
            entry = {'key': key(component, raw), 'values': values(component, raw)}
            if cid == 'damage':
                entry['definition'] = damage_view(u32(raw, 0x3C))
            if cid == 'impact_explosion':
                entry['definition'] = explosion_view(u32(raw, 0x90))
            row['components'][cid] = entry
            group = groups[cid].setdefault(entry['key'], {'values': entry['values'], 'definition':
                entry.get('definition'), 'types': [], 'donors': [], 'unitTypes': [], 'packages': []})
            group['types'].append(kind)
            group['donors'] += [{'name': d, 'type': kind} for d in donors]
            if row['unit']:
                group['unitTypes'].append(kind)
            for package in row['packages']:
                if package not in group['packages']:
                    group['packages'].append(package)
        rows.append(row)

    def empty(cid, group):
        v = group['values']
        if cid == 'visual':
            return all(value in ('0x0000000000000000', 0.0) for value in v.values())
        if cid in ('damage', 'impact_explosion'):
            return not next(iter(v.values()))
        return False

    catalogue = {}
    for cid, component in components.items():
        items = []
        for group_key, group in groups[cid].items():
            usable = [d for d in group['donors']]
            items.append({'key': group_key, 'values': group['values'], 'definition': group['definition'],
                'none': empty(cid, group), 'types': group['types'], 'unitTypes': group['unitTypes'],
                'donors': usable, 'packages': group['packages'],
                # A visual from a row with a unit cannot go on a unit-less base: its unit (LATE_LOOKUP) stays the base's.
                'unitlessDonors': [d for d in usable if d['type'] not in group['unitTypes']]})
        items.sort(key=lambda g: (g['none'], -len(g['donors']), g['types'][0]))
        catalogue[cid] = {'descriptor': {k: component[k] for k in ('id', 'name', 'assets', 'constraints', 'meaning',
            'evidence', 'live')}, 'members': component['members'], 'groups': items}

    def unique(cid, donors_only=False):
        return sum(1 for g in catalogue[cid]['groups'] if not g['none'] and (g['donors'] or not donors_only))

    summary = {'rows': len(rows), 'liveRowsMatchingDatalibrary': (TYPES - 1) - len(mismatched),
        'rowsWithIdentity': sum(1 for r in rows if r['identities']),
        'rowsWithRuntimeDonor': sum(1 for r in rows if r['runtimeDonors']),
        'runtimeDonors': len({d for r in rows for d in r['runtimeDonors']}),
        'rowsWithUnit': sum(1 for r in rows if r['unit']),
        'unique': {cid: unique(cid) for cid in catalogue},
        'uniqueAmongRuntimeDonors': {cid: unique(cid, True) for cid in catalogue},
        'unitlessVisualsAmongRuntimeDonors': sum(1 for g in catalogue['visual']['groups']
            if not g['none'] and g['unitlessDonors'])}
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'snapshot': SNAPSHOT,
        'source': {'datalibrary': 'generated_projectile_settings / explosion / damage (pinned)',
            'policy': 'domains/projectile_rows.lua', 'identities': ['domains/attack_outputs.lua',
            'domains/event_natives.lua'], 'packages': 'domains/package_residency.lua'},
        'liveMismatches': mismatched, 'summary': summary, 'components': catalogue, 'rows': rows,
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
