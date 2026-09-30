"""Stun-field donors: what produces an area stun natively, and which of it a ProgrammableAmmo host can fire. Read-only.

Question (SpeargunGasStunTest, 2026-09-30): the S-11 Speargun's second mode fired the GL-52 De-Escalator projectile,
which arcs (heavy electric damage) instead of leaving the crowd-control stun field the test wanted. What is a stun
field in the native data, and which donor leaves one where it lands?

Proven on build F5FEE03DCFDB from the pinned type library and the settings and entity tables of the retained
snapshot:

1. A lingering field is a member of the explosion, not a separate entity or a status of its own. ExplosionInfo +100
   is a StatusEffectTemplateType (hidden name length 24: persistent_status_volume) and +104 an f32 (length 25:
   status_volume_effect_time). An explosion with a non-zero template leaves a status volume of that template for that
   many seconds. The Speargun's own gas cloud is exactly this: its spear (ProjectileType 125) ends in explosion 97,
   template Gas, 10 s.
2. The EMS field is the StaticField template. Every explosion carrying it has the same DamageInfo (Stun Medium,
   strength 100, no damage): the A/M-23 EMS Mortar Sentry shell's expiry explosion, the Orbital EMS Strike shell's
   impact explosion (also detonated by the emp_grenade throwable), a mission artillery shell's and an unowned
   projectile's.
3. The G-23 Stun grenade is not a field: a thrown entity (flashbang) whose ExplosiveComponent detonates one explosion
   (Stun Large, strength 25) and leaves no volume. It is an entity, not a ProjectileType, so a host cannot fire it as
   its function projectile.
4. Stun explosions and volumes with no typed owner in the entity or settings tables (for example a Freezing volume
   with Stun Medium, a Stun Massive burst) are requested by code or by data outside those tables (environment
   hazards among them): no owner, no package, not selectable.
5. Donor rule for function_ammo.projectile: a ProjectileType owned by a component the write engine re-proves live
   (ProjectileWeaponComponentData +0, unique owner) whose entity owns a loadout package Runtime can load. Only the EMS
   Mortar shell qualifies. The Orbital EMS shell is owned by a BombardmentComponent, which the runtime profile does
   not describe; the other StaticField shells have no loadout owner.

Output: research/stun-field-donors-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import build_profile  # noqa: E402
from research_attachment_presets import _module_sources, _lua  # noqa: E402
import research_attack_outputs as attack_outputs  # noqa: E402
import research_package_residency as residency  # noqa: E402
import research_throwable_authoring as throwables  # noqa: E402
import research_weapon_fire_modes as fire_modes  # noqa: E402
from tools.lua_runner import execute  # noqa: E402

OUTPUT = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
STATUS = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
STRATAGEMS = (ROOT / 'research/offensive-stratagem-runtime-F5FEE03DCFDB.json',
    ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json')
# (struct, offset): (member, hidden name length, storage, enum type)
LAYOUT = {('ExplosionInfo', 100): ('persistent_status_volume', 24, 'ENUM_UINT32', 'StatusEffectTemplateType'),
    ('ExplosionInfo', 104): ('status_volume_effect_time', 25, 'FP32', None),
    ('ExplosionInfo', 4): ('damage_type', 11, 'ENUM_UINT32', 'DamageInfoType'),
    ('ProjectileInfo', 144): ('impact explosion', 24, 'ENUM_UINT32', 'ExplosionType'),
    ('ProjectileInfo', 156): ('expiry explosion', 21, 'ENUM_UINT32', 'ExplosionType')}
# DamageInfo status slots (research/status-effects-F5FEE03DCFDB.json): type +44 + 8n, strength +48 + 8n.
STATUS_SLOTS = 4
# The questions the live report named, each answered by one native object.
CANDIDATES = [
    {'id': 'speargun_gas', 'name': 'S-11 Speargun gas cloud (control)', 'kind': 'projectile', 'type': 125},
    {'id': 'ems_mortar', 'name': 'A/M-23 EMS Mortar Sentry shell', 'kind': 'projectile', 'type': 154,
        'stratagem': 'A/M-23 EMS Mortar Sentry'},
    {'id': 'orbital_ems', 'name': 'Orbital EMS Strike shell', 'kind': 'projectile', 'type': 74,
        'stratagem': 'Orbital EMS Strike'},
    {'id': 'artillery_ems', 'name': 'Mission artillery EMS shell', 'kind': 'projectile', 'type': 92},
    {'id': 'unowned_static_field', 'name': 'Unowned StaticField projectile', 'kind': 'projectile', 'type': 29},
    {'id': 'g23_stun', 'name': 'G-23 Stun grenade', 'kind': 'explosion', 'type': 220, 'throwable': 'G-23 Stun'},
    {'id': 'emp_grenade', 'name': 'emp_grenade throwable', 'kind': 'explosion', 'type': 188},
    {'id': 'gl52_arc', 'name': 'GL-52 De-Escalator arc grenade (the tested donor)', 'kind': 'projectile', 'type': 222},
]
PROFILE_COMPONENTS = ('ProjectileWeaponComponentData',)


def prove_layout(native):
    lib = native.typelib_module
    out = []
    for (struct_name, offset), (label, length, storage, enum) in LAYOUT.items():
        members = {m['offset64']: m for m in lib.layout(native.typelib, struct_name, structured=True)['members']}
        member = members[offset]
        if not member['name'].endswith('inferred_length=' + str(length)) or member['storage'] != storage:
            raise ValueError(f'{struct_name} +{offset} ({label}) changed')
        if enum and member['type_hash'] != native.probe.dl_hash(enum):
            raise ValueError(f'{struct_name} +{offset} is no longer {enum}')
        out.append({'struct': struct_name, 'offset': offset, 'member': label, 'nameLength': length,
            'storage': storage, 'type': enum})
    return out


def snapshot_rows():
    """Every explosion, projectile and damage row of the retained snapshot (production resolver)."""
    preload = '\n'.join('package.preload[' + _lua(n) + ']=function(...) return assert(loadstring(' + _lua(b)
        + ',' + _lua(n) + '))(...) end' for n, b in _module_sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(build_profile.SNAPSHOT)) + r''',{
  expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
 local reader=Reader.new(source)
 local roots=discover.locate(source,reader,profile,{projectile=true,damage=true,explosion=true})
 local out={explosions={},projectiles={},damage={}}
 for t,r in pairs(roots.explosion.records)do
  local x=r.bytes
  out.explosions[tostring(t)]={type=t,damage=b.u32(x,4),inner=b.value(x,16,'f32'),outer=b.value(x,20,'f32'),
   shockwave=b.value(x,24,'f32'),shrapnel=b.u32(x,80),arc=b.u32(x,120),volume=b.u32(x,100),
   seconds=b.value(x,104,'f32')}
 end
 for t,r in pairs(roots.projectile.records)do
  local x=r.bytes
  out.projectiles[tostring(t)]={type=t,damage=b.u32(x,60),velocity=b.value(x,32,'f32'),impact=b.u32(x,144),
   expiry=b.u32(x,156),settings={group=r.group,row=r.row,recordType=r.kind,settingsType=r.settings_type}}
 end
 for t,r in pairs(roots.damage.records)do
  local x=r.bytes;local slots={}
  for n=0,3 do local s=b.u32(x,44+8*n);if s~=0 then slots[#slots+1]={type=s,strength=b.value(x,48+8*n,'f32')}end end
  out.damage[tostring(t)]={type=t,standard=b.u32(x,4),durable=b.u32(x,8),status=slots}
 end
 reader.verify();source.close()
 return out
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''
    return json.loads(execute(program.encode()))


def rounded(value):
    return round(value, 3) if isinstance(value, float) else value


def main():
    fire_native = fire_modes.entity_research.Native()
    layout = prove_layout(fire_native)
    # Template 0 is None (no volume); unnamed templates keep their number.
    templates = {int(k): v for k, v in fire_modes.enum_names(fire_native, 'StatusEffectTemplateType').items() if int(k)}
    statuses = {s['nativeType']: s['semanticId'] for s in json.loads(STATUS.read_text(encoding='utf-8'))['statuses']}
    rows = snapshot_rows()
    explosions, projectiles, damage = rows['explosions'], rows['projectiles'], rows['damage']
    native = throwables.Native()
    references = native.reference_index()
    paths = native.paths

    def owners(kind, record_type):
        found, orphan = throwables.root_owners(references, kind, record_type)
        direct = [{'via': item.get('component') or item.get('settings'), 'offset': item['offset']}
            for item in throwables.consumers(references, kind, record_type)]
        return {'entities': sorted((paths.path(r) or f'0x{r:016X}').rsplit('/', 1)[-1] for r in found),
            'direct': sorted({(d['via'], d['offset']) for d in direct}), 'settingsOnly': orphan}

    def status_list(damage_type):
        row = damage.get(str(damage_type)) or {}
        return [{'status': statuses.get(s['type'], s['type']), 'strength': rounded(s['strength'])}
            for s in row.get('status') or []]

    def explosion_view(t):
        e = explosions[str(t)]
        return {'type': t, 'volume': templates.get(e['volume']) or e['volume'] or None,
            'volumeSeconds': rounded(e['seconds']) if e['volume'] else None,
            'radii': [rounded(e['inner']), rounded(e['outer']), rounded(e['shockwave'])],
            'damage': {'standard': (damage.get(str(e['damage'])) or {}).get('standard'),
                'status': status_list(e['damage'])}, 'arc': bool(e['arc']), 'shrapnel': e['shrapnel']}

    by_explosion = {}
    for p in projectiles.values():
        for role in ('impact', 'expiry'):
            if p[role]:
                by_explosion.setdefault(p[role], []).append({'projectile': p['type'], 'role': role})
    volumes = []
    for e in sorted(explosions.values(), key=lambda e: (e['volume'], e['type'])):
        if e['volume']:
            volumes.append(dict(explosion_view(e['type']), projectiles=by_explosion.get(e['type'], []),
                owners=owners('explosion', e['type'])))
    stuns = []
    for e in sorted(explosions.values(), key=lambda e: e['type']):
        applied = [s for s in status_list(e['damage']) if str(s['status']).startswith(('stun', 'tornado_stun'))]
        if applied:
            view = owners('explosion', e['type'])
            stuns.append({'explosion': e['type'], 'status': applied,
                'volume': templates.get(e['volume']) or e['volume'] or None, 'radius': rounded(e['outer']),
                'projectiles': by_explosion.get(e['type'], []), 'owners': view,
                'owned': bool(view['entities'] or by_explosion.get(e['type']))})

    # Stratagem names by payload resource (the stratagem research roots).
    stratagem_of = {}
    for path in STRATAGEMS:
        for item in json.loads(path.read_text(encoding='utf-8'))['stratagems']:
            for payload in (item.get('currentRoot') or {}).get('payloads') or []:
                stratagem_of[int(payload, 16)] = (item['name'], (item.get('currentRoot') or {}).get('package'))
    bundles = residency.bundle_database()
    entity_native = paths
    view = native.view
    weapon_owners = view.component('ProjectileWeaponComponentData').owners
    loadout_owners = view.component('LoadoutPackageComponentData').owners

    candidates, donors = [], []
    for item in CANDIDATES:
        entry = {'id': item['id'], 'name': item['name']}
        if item['kind'] == 'projectile':
            p = projectiles[str(item['type'])]
            chain = [dict(explosion_view(p[role]), role=role) for role in ('impact', 'expiry') if p[role]]
            fields = [c for c in chain if c['volume']]
            entry.update(projectileType=item['type'], velocity=rounded(p['velocity']), chain=chain,
                owners=owners('projectile', item['type']),
                effect=('persistent status volume (' + ', '.join(f"{c['volume']} {c['volumeSeconds']} s, radius "
                    f"{c['radii'][1]}" for c in fields) + ') left by its ' + '/'.join(c['role'] for c in fields)
                    + ' explosion') if fields else ('arc on impact' if any(c['arc'] for c in chain) else
                    'explosion without a lasting field' if chain else 'direct hit only'))
            owned = [r for r in weapon_owners if struct.unpack_from('<I', view.record(
                'ProjectileWeaponComponentData', r)['bytes'], 0)[0] == item['type']]
            entry['projectileWeaponOwners'] = len(owned)
            if len(owned) == 1:
                resource = owned[0]
                record = view.record('ProjectileWeaponComponentData', resource)
                package = None
                if resource in loadout_owners:
                    pid = struct.unpack_from('<Q', view.record('LoadoutPackageComponentData', resource)['bytes'], 8)[0]
                    name = entity_native.path(pid)
                    if name is None and entity_native.path(resource):
                        # Generated loadout packages are named after their entity: accepted only on an exact hash.
                        candidate = 'packages/generated/loadout/' + entity_native.path(resource).rsplit('/', 1)[-1]
                        name = candidate if residency.murmur64a(candidate.encode()) == pid else None
                    package = {'package': f'0x{pid:016X}', 'name': name, 'via': 'own_loadout_package',
                        'inBundleDatabase': pid in bundles['packages']}
                entry['owner'] = {'resource': f'0x{resource:016X}', 'path': entity_native.path(resource),
                    'stratagem': stratagem_of.get(resource, (None,))[0],
                    'component': 'ProjectileWeaponComponentData',
                    'componentIdentity': {'recordIndex': record['recordIndex'], 'indexRow': record['indexRow'],
                        'ownerCount': record['ownerCount'], 'uniqueOwner': record['ownerCount'] == 1},
                    'entityRow': fire_native.entity_row(resource), 'package': package}
        else:
            entry.update(explosion=explosion_view(item['type']), owners=owners('explosion', item['type']))
            entry['effect'] = ('persistent status volume' if entry['explosion']['volume'] else
                'single status burst (no lasting field)')
        candidates.append(entry)

    decisions = {
        'speargun_gas': ('control', 'Mode A: the Speargun spear itself. Its gas cloud is a Gas status volume left by its '
            'expiry explosion.'),
        'ems_mortar': ('supported', 'A ProjectileType fired by the EMS Mortar turret\'s own ProjectileWeapon +0 (unique '
            'owner), whose expiry explosion leaves a StaticField volume applying Stun Medium; the turret owns its own '
            'loadout package. The write engine re-proves the owner record and loads the package before writing.'),
        'orbital_ems': ('blocked', 'The shell leaves the largest StaticField, but its owner is the orbital\'s '
            'BombardmentComponent (+64), which the runtime profile does not describe, so the source cannot be re-proven '
            'live. Adding that component to the profile would make it a donor.'),
        'artillery_ems': ('blocked', 'Owned by a mission objective shell component, not by a loadout item: no package '
            'Runtime can name.'),
        'unowned_static_field': ('blocked', 'No entity or settings row references this projectile: no owner and no '
            'package.'),
        'g23_stun': ('not_a_projectile', 'A thrown entity whose ExplosiveComponent detonates one Stun Large burst (no '
            'lasting field). A ProgrammableAmmo host fires a ProjectileType, and this is an entity; spawning it would '
            'be the function entity member (+584), which Runtime does not write.'),
        'emp_grenade': ('not_a_projectile', 'A thrown entity that detonates the Orbital EMS static-field explosion; the '
            'same entity limit as the G-23.'),
        'gl52_arc': ('supported_not_a_field', 'The tested donor: its impact explosion arcs (electric damage) and leaves '
            'no field. Works as a function projectile (live, 2026-09-30) but is not a stun field.')}
    for entry in candidates:
        entry['decision'], entry['reason'] = decisions[entry['id']]
        owner = entry.get('owner') or {}
        if entry['decision'] == 'supported':
            if not (owner.get('componentIdentity', {}).get('uniqueOwner') and (owner.get('package') or {}).get(
                    'inBundleDatabase') and owner.get('stratagem')):
                raise ValueError(entry['id'] + ': a supported donor needs a unique owner, a loadable package and a name')
            projectile = projectiles[str(entry['projectileType'])]
            chain = {'impact': explosions.get(str(projectile['impact'])), 'expiry': explosions.get(str(projectile['expiry']))}
            row = {'impact': {'arc': chain['impact']['arc'], 'shrapnel': chain['impact']['shrapnel']}
                if chain['impact'] else None, 'expiry': {'type': chain['expiry']['type']} if chain['expiry'] else None}
            donors.append({'id': entry['id'], 'name': owner['stratagem'], 'ownerKind': 'stratagem',
                'label': entry['name'], 'resource': owner['resource'], 'entityRow': owner['entityRow'],
                'component': owner['component'], 'componentIdentity': owner['componentIdentity'],
                'projectileType': entry['projectileType'], 'settings': projectile['settings'],
                'compatibilityClass': attack_outputs.projectile_class(row), 'package': owner['package'],
                'field': [c for c in entry['chain'] if c['volume']][0], 'referenceScope': ['function_ammo.projectile']})
    result = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'snapshot': build_profile.SNAPSHOT_NAME,
        'question': 'Which native object leaves a stun (EMS) field where it lands, and can a ProgrammableAmmo host fire it?',
        'model': {
            'field': 'A lingering area effect is ExplosionInfo persistent_status_volume (+100, StatusEffectTemplateType) '
                'and status_volume_effect_time (+104, seconds): the explosion leaves a volume of that template.',
            'ems': 'The EMS field is the StaticField template; its explosions apply Stun Medium (strength 100) and no '
                'damage.',
            'stunGrenade': 'The G-23 Stun is a single Stun Large burst from a thrown entity, not a field.',
            'classification': {'explosion': 'the status burst itself (DamageInfo status slots of the explosion)',
                'status': 'Stun Small / Medium / Large / Massive: global StatusEffectSettings rows the damage applies',
                'volume': 'the persistent status volume an explosion leaves (StaticField, Gas, Smoke, Freezing, ...)',
                'entity': 'thrown grenades (G-23, emp_grenade) are entities with an ExplosiveComponent',
                'secondaryImpactObject': 'none: no stun source spawns a separate object on impact'}},
        'typeLibrary': layout, 'templates': {str(k): v for k, v in sorted(templates.items()) if v and v != 'Count'},
        'volumes': volumes, 'stunExplosions': stuns, 'candidates': candidates, 'donors': donors,
        'summary': {'volumes': len(volumes), 'staticFieldExplosions': sum(v['volume'] == 'StaticField' for v in volumes),
            'stunExplosions': len(stuns), 'unownedStunExplosions': sum(not s['owned'] for s in stuns),
            'supportedDonors': [d['id'] for d in donors]}}
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result['summary'], indent=1))
    for entry in candidates:
        print(entry['id'], entry['decision'], entry.get('effect'))


if __name__ == '__main__':
    main()
