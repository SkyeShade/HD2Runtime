"""Native attack-output composition of player and support weapons. Read-only research.

Question: can a magazine-fed ballistic weapon (AR-23 Liberator) keep its own fire control and resources while its
attack produces a fundamentally different output (continuous beam, Trident multi-beam, EAT-700 napalm rocket, ARC-3
arc)? This records what the native data says:

1. Type references (pinned type library): every struct member typed as a ProjectileType, BeamType, ArcType or
   ExplosionType reference. Each output family has its own enum reference space and its own weapon component; the
   only settings-level bridges are projectile -> explosion (impact / expiry), explosion -> projectile (shrapnel),
   explosion -> arc (+120) and beam -> explosion (+96). Nothing references a BeamType except the beam weapon itself.
2. Weapon composition (entity settings): each weapon entity owns exactly one output-family component
   (ProjectileWeapon, BeamWeapon, ArcWeapon, SprayWeapon, MeleeWeapon) next to its fire-control and resource
   components (WeaponData, WeaponMagazine / WeaponRounds / WeaponHeat / WeaponCharge, WeaponReload).
3. Outputs: every family component's reference, its settings row (production resolver, retained snapshot), its chain
   and its native consumers (migration Scope index).
4. Liberator compositions for the four requested outputs, each SUPPORTED or BLOCKED with the structural reason.

`projectileHost` is only the structural pre-filter (magazine-fed, empty magazine pattern, no rounds, charge or heat).
It is not host eligibility: a live test showed the Liberator ignores its ProjectileWeapon +0 because its default
ammunition delta overwrites it at weapon build. Which member a host fires is classified by
scripts/research_active_projectile_sources.py, and the catalog's hosts come from there.

Output: research/attack-outputs-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import build_profile  # noqa: E402
from migration import build_view, engine  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
from research_attachment_presets import _module_sources, _lua  # noqa: E402
from tools.lua_runner import execute  # noqa: E402

OUTPUT = ROOT / 'research/attack-outputs-F5FEE03DCFDB.json'
FAMILY_COMPONENTS = {'ProjectileWeaponComponentData': ('projectile', 0, 'ProjectileType'),
    'BeamWeaponComponentData': ('beam', 0, 'BeamType'), 'ArcWeaponComponentData': ('arc', 0, 'ArcType'),
    'SprayWeaponComponentData': ('spray', 200, 'DamageInfoType'),
    'MeleeWeaponComponentData': ('melee', 12, 'DamageInfoType')}
FIRE_RESOURCE = ('WeaponDataComponentData', 'WeaponMagazineComponentData', 'WeaponRoundsComponentData',
    'WeaponHeatComponentData', 'WeaponChargeComponentData', 'WeaponReloadComponentData',
    'WeaponWindUpComponentData', 'WeaponCustomizationComponentData')
# Members of the family components that carry fire control or resource behaviour of their own (filediver names,
# checked against the pinned type library's offsets and hidden name lengths).
FAMILY_OWNED = {
    'ProjectileWeaponComponent': [(0, 'projectile_type (ProjectileType)'), (8, 'rounds per minute'),
        (36, 'infinite ammo'), (576, 'second ProjectileType')],
    'BeamWeaponComponent': [(0, 'beam_type (BeamType)'), (16, 'heat buildup (WeaponHeatBuildup)'),
        (100, 'beam fire mode (BeamFireMode)'), (104, 'int, len 16'), (108, 'int, len 19'), (112, 'f32, len 13')],
    'ArcWeaponComponent': [(0, 'arc_type (ArcType)'), (4, 'rounds per minute'), (8, 'infinite ammo'),
        (9, 'RPC-synced fire events')],
}
SUBJECTS = {'AR-23 Liberator': 'host', 'LAS-98 Laser Cannon': 'LAS Beam', 'LAS-13 Trident': 'Trident',
    'EAT-700 Expendable Napalm': 'EAT-700 Napalm', 'ARC-3 Arc Thrower': 'ARC-3 Arc',
    'GL-52 De-Escalator': 'arc on impact (native explosion arc)', 'ARC-12 Blitzer': 'arc without charge'}


def type_references(library, names):
    wanted = {build_view.dl_hash(n): n for n in ('ProjectileType', 'BeamType', 'ArcType', 'ExplosionType')}
    refs = {name: [] for name in wanted.values()}
    for type_hash in sorted(library.index):
        try:
            layout = library.layout(type_hash)
        except ValueError:
            continue
        for member in layout['members']:
            if member['type_hash'] in wanted:
                refs[wanted[member['type_hash']]].append({'type': names.get(type_hash, f'0x{type_hash:08X}'),
                    'offset': member['offset64'], 'array': member['array_or_bits'] or None})
    for items in refs.values():
        items.sort(key=lambda r: (r['type'], r['offset']))
    return refs


def resolve_settings(projectiles, beams, arcs):
    """Settings rows with identities and chains (production resolver on the retained snapshot)."""
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
 local roots=discover.locate(source,reader,profile,{projectile=true,damage=true,explosion=true,arc=true,beam=true})
 local function id(r)return r and {group=r.group,row=r.row,recordType=r.kind,settingsType=r.settings_type}end
 local function explosion(t)
  local r=roots.explosion.records[t];if not r then return nil end
  return {type=t,settings=id(r),damage=b.u32(r.bytes,4),shrapnel=b.u32(r.bytes,84),arc=b.u32(r.bytes,120),
   radii={b.value(r.bytes,16,'f32'),b.value(r.bytes,20,'f32'),b.value(r.bytes,24,'f32')}}
 end
 local out={projectiles={},beams={},arcs={},explosionArcs={}}
 for _,t in ipairs(''' + _lua(projectiles) + r''')do local r=roots.projectile.records[t]
  if r then local i,e=b.u32(r.bytes,144),b.u32(r.bytes,156)
   out.projectiles[tostring(t)]={type=t,settings=id(r),damage=b.u32(r.bytes,60),velocity=b.value(r.bytes,32,'f32'),
    mass=b.value(r.bytes,36,'f32'),impact=i~=0 and explosion(i)or nil,expiry=e~=0 and explosion(e)or nil}
  end
 end
 for _,t in ipairs(''' + _lua(beams) + r''')do local r=roots.beam.records[t]
  if r then out.beams[tostring(t)]={type=t,settings=id(r),radius=b.value(r.bytes,4,'f32'),
   length=b.value(r.bytes,8,'f32'),damage=b.u32(r.bytes,12),explosion=b.u32(r.bytes,96)}end
 end
 for _,t in ipairs(''' + _lua(arcs) + r''')do local r=roots.arc.records[t]
  if r then out.arcs[tostring(t)]={type=t,settings=id(r),speed=b.value(r.bytes,4,'f32'),
   distance=b.value(r.bytes,8,'f32'),chain=b.u32(r.bytes,28),split=b.u32(r.bytes,32),damage=b.u32(r.bytes,36)}end
 end
 for t,r in pairs(roots.explosion.records)do
  local a=b.u32(r.bytes,120)
  if a~=0 then out.explosionArcs[#out.explosionArcs+1]={explosion=t,arc=a,settings=id(r)}end
 end
 table.sort(out.explosionArcs,function(x,y)return x.explosion<y.explosion end)
 reader.verify();source.close()
 return out
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''
    return json.loads(execute(program.encode()))


def projectile_class(row):
    """The same structural classes the projectile-reference swap already uses, plus explosive_arc."""
    impact, expiry = row.get('impact'), row.get('expiry')
    if not impact and not expiry:
        return 'conventional_plain'
    if impact and impact.get('arc'):
        return 'explosive_arc'
    if impact and impact.get('shrapnel'):
        return 'explosive_shrapnel'
    return 'explosive_impact_and_expiry' if impact and expiry else 'explosive_impact'


def weapons():
    """(name, kind, resource) for every uniquely resolved player, support and mounted weapon. Mounted weapons (vehicles,
    Exosuits, Guard Dog drones, emplacements) are keyed '<vehicle> / <mount>' like sdk/VehicleWeaponCapabilities.json;
    two mounts may carry the same weapon entity."""
    items = []
    for weapon in json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())['weapons']:
        if weapon['resolution'] == 'UNIQUE' and weapon['resources']:
            items.append((weapon['name'], 'player_weapon', weapon['resources'][0]))
    text = (ROOT / 'domains/support_weapon_authoring.lua').read_text(encoding='utf-8')
    for weapon in json.loads((ROOT / 'sdk/SupportWeaponAuthoringCapabilities.json').read_text())['weapons']:
        start = text.find('["' + weapon['name'] + '"]={')
        if start < 0 or not weapon.get('writable'):
            continue
        match = re.search(r'\["attackResource"\]="(0x[0-9A-F]+)"', text[start:start + 4000])
        resources = re.search(r'\["resources"\]=\{"(0x[0-9A-F]+)"', text[start:start + 400000])
        resource = (match or resources).group(1) if (match or resources) else None
        if resource:
            items.append((weapon['name'], 'support_weapon', resource))
    text = (ROOT / 'domains/vehicle_weapon_authoring.lua').read_text(encoding='utf-8')
    for vehicle in json.loads((ROOT / 'sdk/VehicleWeaponCapabilities.json').read_text())['vehicles']:
        for mount in vehicle['mounts']:
            if not mount.get('weapon'):
                continue
            key = mount['weapon']['key']
            start = text.find('["' + key + '"]={')
            if start < 0:
                continue
            # attackResource sorts first among the entry's keys; the window stays inside the entry.
            match = re.match(r'\["' + re.escape(key) + r'"\]=\{\["attackResource"\]="(0x[0-9A-F]+)"', text[start:])
            if match:
                items.append((key, 'vehicle_weapon', match.group(1)))
    return items


def mounted_asset_keys():
    """Mounted weapon entity resource -> its asset catalog key (research/package-residency-F5FEE03DCFDB.json)."""
    residency = json.loads((ROOT / 'research/package-residency-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    return {int(item['resource'], 16): key for key, item in residency['catalog'].items()
        if key.startswith('mounted_weapon/') and item.get('resource')}


def build():
    native = entity_research.Native()
    library = build_view.TypeLibrary((build_profile.FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes())
    refs = type_references(library, native.names)
    assets = {o['key']: o['packageDependency'] for o in
        json.loads((ROOT / 'sdk/AssetDependencyCapabilities.json').read_text())['objects']}
    entries, projectile_types, beam_types, arc_types = [], set(), set(), set()
    mounted_keys = mounted_asset_keys()
    for name, kind, resource in weapons():
        asset_key = mounted_keys.get(int(resource, 16)) if kind == 'vehicle_weapon' else kind + '/' + name
        components = {c['name']: c for c in native.report(resource)['components'] if c['resolved'] and c['name']}
        families = [c for c in FAMILY_COMPONENTS if c in components]
        if len(families) != 1:
            continue
        component = families[0]
        family, offset, enum = FAMILY_COMPONENTS[component]
        record = native.record(component, components[component]['record_index'])
        ownership = native.ownership(components[component])
        output = struct.unpack_from('<I', record, offset)[0]
        entry = {'weapon': name, 'kind': kind, 'resource': resource, 'entityRow': native.entity_row(int(resource, 16)),
            'family': family, 'component': component, 'reference': {'enum': enum, 'offset': offset, 'value': output},
            'componentIdentity': {'recordIndex': components[component]['record_index'],
                'indexRow': components[component]['index_row'], 'ownerCount': ownership['ownerCount'],
                'uniqueOwner': ownership['uniqueOwner']},
            'fireResource': sorted(c for c in components if c in FIRE_RESOURCE),
            'package': (assets.get(asset_key) or {}).get('package'),
            'packageAutoLoad': (assets.get(asset_key) or {}).get('autoLoadSupported'), 'assetKey': asset_key}
        if family == 'projectile':
            projectile_types.add(output)
            if 'WeaponRoundsComponentData' in components:
                rounds = native.record('WeaponRoundsComponentData', components['WeaponRoundsComponentData']['record_index'])
                entry['roundsProjectiles'] = list(struct.unpack_from('<II', rounds, 64))
            if 'WeaponMagazineComponentData' in components:
                magazine = native.record('WeaponMagazineComponentData',
                    components['WeaponMagazineComponentData']['record_index'])
                entry['magazinePatternEntries'] = sum(1 for v in struct.unpack_from('<32I', magazine, 4) if v) + (
                    1 if struct.unpack_from('<I', magazine, 132)[0] else 0)
            entry['rpm'] = round(struct.unpack_from('<f', record, 8)[0], 3)
            entry['infiniteAmmo'] = bool(record[36])
        elif family == 'beam':
            beam_types.add(output)
            entry.update(beamFireMode=struct.unpack_from('<I', record, 100)[0],
                beamIntegers=list(struct.unpack_from('<ii', record, 104)), beamPulse=round(struct.unpack_from('<f', record, 112)[0], 3))
        elif family == 'arc':
            arc_types.add(output)
            entry.update(rpm=round(struct.unpack_from('<f', record, 4)[0], 3), infiniteAmmo=bool(record[8]))
        # Structural pre-filter only (magazine-fed: empty magazine pattern, no rounds ammo types, no charge / heat
        # levels). Whether +0 is the fired projectile is research_active_projectile_sources.py's classification.
        entry['projectileHost'] = (family == 'projectile' and 'WeaponMagazineComponentData' in components
            and entry.get('magazinePatternEntries') == 0 and not any(c in components for c in
                ('WeaponRoundsComponentData', 'WeaponChargeComponentData', 'WeaponHeatComponentData')))
        entries.append(entry)
    settings = resolve_settings(sorted(projectile_types), sorted(beam_types), sorted(arc_types | {15, 6}))
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    scope = engine.Scope(view)

    def consumers(kind, value):
        return sorted((native.path(r) or f'0x{r:016X}').rsplit('/', 1)[-1] for r in scope.of(kind, value))

    for entry in entries:
        value = entry['reference']['value']
        if entry['family'] == 'projectile':
            row = settings['projectiles'].get(str(value))
            entry['output'] = row
            entry['compatibilityClass'] = projectile_class(row) if row else None
        elif entry['family'] == 'beam':
            entry['output'] = settings['beams'].get(str(value))
        elif entry['family'] == 'arc':
            entry['output'] = settings['arcs'].get(str(value))
        if entry['family'] in ('projectile', 'beam', 'arc'):
            entry['outputConsumers'] = consumers(entry['family'], value)
    for item in settings['explosionArcs']:
        item['consumers'] = consumers('explosion', item['explosion'])
        item['arcRow'] = settings['arcs'].get(str(item['arc']))
    by_name = {e['weapon']: e for e in entries}
    host = by_name['AR-23 Liberator']
    cases = {
        'LAS Beam': {'donor': 'LAS-98 Laser Cannon', 'status': 'BLOCKED', 'reason': (
            'A beam is fired only by a BeamWeaponComponent (BeamType at +0). No projectile, explosion or other '
            'settings member references a BeamType, and the Liberator entity owns a ProjectileWeaponComponent, not a '
            'BeamWeaponComponent. The beam component also owns its own firing behaviour (BeamFireMode, heat buildup) '
            'and the LAS-98 draws on WeaponHeat, which the Liberator does not have. A beam output would need the '
            'entity component composition itself changed, which is not a reference write and is not generated.')},
        'Trident': {'donor': 'LAS-13 Trident', 'status': 'BLOCKED', 'reason': (
            'Same family boundary as the LAS beam. The Trident is one BeamWeaponComponent (BeamType 6) in BeamFireMode '
            '6 (the continuous beams use 4), with +104 = 300, +108 = 2 and +112 = 0.15 where the continuous beams have '
            '60 / 1 / 0, and a single-fire audio event instead of loop start/stop. No member counts beams: BeamInfo '
            'has none, and the BeamPrisms type (light/heavy BeamType with heat multipliers) exists in the type library '
            'but is embedded in no struct in this build. Beam count, spread, tick and pulse members are unidentified '
            'and stay read-only.')},
        'EAT-700 Napalm': {'donor': 'EAT-700 Expendable Napalm', 'status': 'SUPPORTED', 'reason': (
            'Same output family: the EAT-700 fires through its own ProjectileWeaponComponent (+0 ProjectileType), and '
            'everything the rocket does hangs off its own projectile row: impact explosion, napalm submunition '
            'projectile and its explosion, and the fire statuses. The Liberator fires the projectile of its default '
            'ammunition (RIFLE 5,5x50mm. FULL METAL JACKET), whose entity delta overwrites its ProjectileWeapon +0 at '
            'weapon build, so the composition writes that ammunition projectile, not the dormant +0. Its structural '
            'class (explosive_shrapnel) differs from the Liberator\'s (conventional_plain): a cross-class reference '
            'that needs allow_unverified_reference and allow_unverified_effect.'),
            'writes': ['host default ammunition delta (weapon:ammunition():projectile(), ammunition.projectile)']},
        'ARC-3 Arc': {'donor': 'ARC-3 Arc Thrower', 'status': 'BLOCKED', 'reason': (
            'An arc is emitted by an ArcWeaponComponent (ArcType at +0; it also owns RPM and infinite ammo) or by an '
            'explosion (ExplosionInfo +120 ArcType). The ARC-3 arc (ArcType 7) is referenced by no explosion; its only '
            'consumer is the ARC-3\'s ArcWeaponComponent. Charge is ARC-3 fire control, not part of the arc output: '
            'the ARC-12 Blitzer fires arcs without a WeaponCharge component. Emitting the ARC-3 arc from the '
            'Liberator\'s muzzle would need an ArcWeaponComponent on the Liberator entity; emitting it at impact would '
            'need a shared explosion row re-pointed at ArcType 7, changing that explosion\'s owners. Neither is '
            'generated.'),
            'nativeAlternative': 'Arc on impact: the GL-52 De-Escalator grenade (projectile 222) whose impact '
                'explosion (41) releases arc 15; a projectile-family swap, supported like the EAT-700.'},
        'Arc on impact': {'donor': 'GL-52 De-Escalator', 'status': 'SUPPORTED', 'reason': (
            'Projectile-family swap to the GL-52 De-Escalator grenade, whose impact explosion releases a native arc '
            '(ExplosionInfo +120), written to the Liberator\'s default ammunition projectile like the EAT-700. '
            'Cross-class (explosive_arc), so allow_unverified_reference and allow_unverified_effect are required.'),
            'writes': ['host default ammunition delta (weapon:ammunition():projectile(), ammunition.projectile)']},
    }
    return {'schemaVersion': 1, 'writes': 0, 'fixtureFallback': 'disabled',
        'model': {
            'weaponComposition': ('A weapon entity owns exactly one output-family component (ProjectileWeapon, '
                'BeamWeapon, ArcWeapon, SprayWeapon or MeleeWeapon) next to fire-control and resource components '
                '(WeaponData, WeaponMagazine / WeaponRounds / WeaponHeat / WeaponCharge, WeaponReload).'),
            'commonOutputAbstraction': False,
            'outputReferences': {'projectile': 'ProjectileWeaponComponent +0 ProjectileType',
                'beam': 'BeamWeaponComponent +0 BeamType', 'arc': 'ArcWeaponComponent +0 ArcType',
                'spray': 'SprayWeaponComponent +200 DamageInfoType', 'melee': 'MeleeWeaponComponent +12 DamageInfoType'},
            'familyOwnedBehaviour': FAMILY_OWNED,
            'bridges': ['ProjectileInfo +144 / +156 -> ExplosionType (impact / expiry)',
                'ExplosionInfo +84 -> ProjectileType (shrapnel / submunition)',
                'ExplosionInfo +120 -> ArcType (an explosion releases an arc)',
                'BeamInfo +96 -> ExplosionType', 'WeaponChargeComponent +200 -> ExplosionType'],
            'noBridgeTo': ['BeamType (only BeamWeaponComponent, BeamInfo and the unembedded BeamPrisms type)']},
        'typeReferences': refs,
        'subjects': {name: dict(by_name[name], role=role) for name, role in SUBJECTS.items() if name in by_name},
        'explosionArcs': settings['explosionArcs'],
        'liberatorCases': cases,
        'hostRetains': {'magazine': 'WeaponMagazineComponent (unchanged)', 'reload': 'WeaponReloadComponent',
            'rpmAndAmmoUse': 'ProjectileWeaponComponent +8 / +36 (host-owned; only the fired projectile changes)',
            'handling': 'WeaponDataComponent (recoil, spread, sway, ergonomics, fire modes)',
            'liberator': {k: host[k] for k in ('rpm', 'infiniteAmmo', 'fireResource', 'magazinePatternEntries',
                'projectileHost')}},
        'summary': {'weapons': len(entries),
            'byFamily': {f: sum(1 for e in entries if e['family'] == f) for f in ('projectile', 'beam', 'arc',
                'spray', 'melee')},
            'projectileHosts': sum(1 for e in entries if e['projectileHost']),
            'explosionArcRows': len(settings['explosionArcs'])},
        'weapons': entries}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))
    for name, case in report['liberatorCases'].items():
        print(f"{name}: {case['status']}")


if __name__ == '__main__':
    main()
