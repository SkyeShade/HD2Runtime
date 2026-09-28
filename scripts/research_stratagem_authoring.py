"""Correlate imported offensive stratagems with the retained current-build snapshot.

This command is read-only. The named JSON reference supplies labels and historical
identity edges only; every scalar and native ownership record comes from current
retained evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)


ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_offensive_stratagems.json'
SNAPSHOT = build_profile.SNAPSHOT
LASER = ROOT.parent / 'StrongerOrbitalLaser'
NAMED_REFERENCE = LASER / 'local_research/external_audit/generated_stratagem_settings.json'
FILEDIVER = LASER / 'local_research/dependencies/filediver-reference'
OUTPUT = ROOT / 'build/offensive-stratagem-research.json'

DEBUG_NAMES = {
    'Orbital Precision Strike': 'ORBITAL. PRECISION STRIKE',
    'Orbital Gatling Barrage': 'ORBITAL. GATLING BARRAGE',
    'Orbital Gas Strike': 'ORBITAL. GAS STRIKE',
    'Orbital 120mm HE Barrage': 'ORBITAL. 120MM HE STRIKE',
    'Orbital Airburst Strike': 'ORBITAL. AIRBURST STRIKE',
    'Orbital Smoke Strike': 'ORBITAL. SMOKE STRIKE',
    'Orbital EMS Strike': 'ORBITAL. STATIC FIELD CONDUTORS',
    'Orbital 380mm HE Barrage': 'ORBITAL. 380MM HE BARRAGE',
    'Orbital Walking Barrage': 'ORBITAL. WALKING BARRAGE',
    'Orbital Laser': 'ORBITAL. LASER',
    'Orbital Napalm Barrage': 'ORBITAL. NAPALM BARRAGE',
    'Orbital Railcannon Strike': 'ORBITAL. RAILCANNON',
    'Eagle Gas Airstrike': 'EAGLE. Gas AIRSTRIKE',
    'Eagle Strafing Run': 'EAGLE. AIR SUPPORT',
    'Eagle Airstrike': 'EAGLE. AIRSTRIKE',
    'Eagle Cluster Bomb': 'EAGLE. CLUSTERBOMBS',
    'Eagle Smoke Strike': 'EAGLE. AIRSTRIKE SMOKE',
    'Eagle Napalm Airstrike': 'EAGLE. NAPALM AIRSTRIKE',
    'Eagle 110mm Rocket Pods': 'EAGLE. 110mm ROCKET PODS',
    'Eagle 500kg Bomb': 'EAGLE. 500KG BOMB',
}

SUPPORT_DEBUG_NAMES = {
    'MG-43 Machine Gun': 'TEAM WEAPONS. MACHINEGUN',
    'M-105 Stalwart': 'TEAM WEAPONS. LIGHT MACHINE GUN',
    'APW-1 Anti-Materiel Rifle': 'TEAM WEAPONS. SNIPER',
    'EAT-17 Expendable Anti-Tank': 'TEAM WEAPONS. EXPENDABLE ANTI-TANK',
    'GR-8 Recoilless Rifle': 'TEAM WEAPONS. RECOILLESS RIFLE',
    'FLAM-40 Flamethrower': 'TEAM WEAPONS. FLAMETHROWER',
    'AC-8 Autocannon': 'TEAM WEAPONS. AUTOMATIC CANNON',
    'MG-206 Heavy Machine Gun': 'TEAM WEAPONS. HEAVY MACHINEGUN',
    'MLS-4X Commando': 'TEAM WEAPONS. COMMANDO',
    'RL-77 Airburst Rocket Launcher': 'TEAM WEAPONS. AIR BURST ROCKET LAUNCHER',
    'FAF-14 Spear': 'TEAM WEAPONS. SPEAR',
    'RS-422 Railgun': 'TEAM WEAPONS. RAILGUN ',
    'StA-X3 W.A.S.P. Launcher': 'TEAM WEAPONS. WASP',
    'LAS-98 Laser Cannon': 'TEAM WEAPONS. LASER CANNON',
    'GL-21 Grenade Launcher': 'TEAM WEAPONS. GRENADE LAUNCHER',
    'ARC-3 Arc Thrower': 'TEAM WEAPONS. ARC THROWER ',
    'LAS-99 Quasar Cannon': 'TEAM WEAPONS. LASER PULSE CANNON',
    'TX-41 Sterilizer': 'TEAM WEAPONS. CHEM GUN',
    'CQC-1 One True Flag': 'TEAM WEAPONS. MELEE FLAG',
    'GL-52 De-Escalator': 'TEAM WEAPONS. GRENADE LAUNCHER TACTICAL',
    'PLAS-45 Epoch': 'TEAM WEAPONS. PLASMA BLASTER',
    'S-11 Speargun': 'TEAM WEAPONS. HARPOON GUN ',
    'EAT-700 Expendable Napalm': 'TEAM WEAPONS. EXPENDABLE NAPALM LAUNCHER',
    'MS-11 Solo Silo': 'TEAM WEAPONS. MINI MISSILE SILO',
    'CQC-9 Defoliation Tool': 'TEAM WEAPONS. CHAINSAW GREATSWORD',
    'M-1000 Maxigun': 'TEAM WEAPONS. MINIGUN',
    'B/MD C4 Pack': 'TEAM WEAPONS. C4',
    'CQC-20 Breaching Hammer': 'TEAM WEAPONS. SLEDGE HAMMER',
    'EAT-411 Leveller': 'TEAM WEAPONS. EXPENDABLE MASSIVE ROCKET LAUNCHER',
    'GL-28 Belt-Fed Grenade Launcher': 'TEAM WEAPONS. BELT FED GRENADE LAUNCHER',
    'B/FLAM-80 Cremator': 'TEAM WEAPONS. HEAVY FLAMETHROWER',
    'MGX-42 Bullet Storm': 'TEAM WEAPONS. EXPENDABLE MACHINEGUN',
    '40-K Meltagun': 'TEAM WEAPONS. SHARK ENERGY WEAPON',
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _lua(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(type(value))


def module_sources():
    result = {}
    for folder in ('api', 'core', 'runtime', 'schemas', 'domains', 'primary_mapper'):
        for path in sorted((ROOT / folder).glob('*.lua')):
            result['hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()] = path.read_text()
    return result


def snapshot_evidence(snapshot: Path):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    sources = module_sources()
    preload = '\n'.join("package.preload[" + _lua(name) + "]=function(...) return assert(loadstring("
        + _lua(body) + ',' + _lua(name) + "))(...) end" for name, body in sources.items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(snapshot)) + r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local reader=require('hd2runtime/runtime/reader').new(source)
local worker=coroutine.create(function()
 local records=require('hd2runtime/core/stratagem').capture_all(source,reader,profile)
 local roots=require('hd2runtime/runtime/discover').locate(source,reader,profile,{projectile=true,
  damage=true,explosion=true,arc=true,beam=true,status='optional'})
 local function hex(bytes)
  local out={};for index=1,#bytes do out[index]=string.format('%02x',bytes:byte(index))end
  return table.concat(out)
 end
 local settings={}
 for _,kind in ipairs({'projectile','damage','explosion','arc','beam','status'})do
  settings[kind]={}
  if roots[kind]then for record_type,record in pairs(roots[kind].records)do
   settings[kind][tostring(record_type)]={group=record.group,row=record.row,
    recordType=record_type,raw=hex(record.bytes)}
  end end
 end
 reader.verify();return {stratagems=records,settings=settings}
end)
local ok,result
repeat ok,result=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,result);source.close()
return require('hd2runtime/primary_mapper/json').encode(result)
'''
    return json.loads(execute(program.encode()))


def named_rows(path: Path):
    document = json.loads(path.read_text(encoding='utf-8'))
    result = {}
    for group_index, group in enumerate(document):
        for group_name, value in group.items():
            for row in value['items']:
                row = dict(row, historicalGroup=group_index, historicalGroupName=group_name)
                result[row['debug_name']] = row
    return result


def typed_references(component, type_hashes):
    found = []

    def visit(fields, path):
        for field in fields:
            field_path = path + [field['offset64']]
            name = type_hashes.get(field['type_hash'])
            if name and 'value' in field:
                values = [value for value in field['value'] if value]
                if values:
                    found.append({'component': component['name'], 'recordType': component['record_type'],
                        'path': field_path, 'referenceClass': name, 'values': values})
            for index, record in enumerate(field.get('records', [])):
                visit(record, field_path + [index])

    visit(component.get('fields', []), [])
    return found


def reviewed_scalars(component):
    if component['name'] != 'OrbitalAbilityComponentData':
        return {}
    wanted = {460, 468, 472, 480}
    result = {}
    def visit(fields, base=0):
        for field in fields:
            absolute = base + field['offset64']
            if absolute in wanted and field.get('value'):
                result[str(absolute)] = field['value'][0]
            for record in field.get('records', []):
                visit(record, absolute)
    visit(component.get('fields', []))
    if set(map(int, result)) != wanted:
        raise ValueError('OrbitalAbility reviewed scalar layout changed')
    return result


def scalar(raw, offset, storage):
    formats = {'u32': '<I', 'i32': '<i', 'f32': '<f'}
    return struct.unpack_from(formats[storage], raw, offset)[0]


def primitive_graph(projectiles, damages, explosions, statuses, root_types):
    """Follow only schema-labelled typed links; no wiki value is used as proof."""
    result = []
    active = set()

    def add_damage(damage_type, path, linkage):
        if not damage_type:
            return None
        record = damages.get(damage_type)
        if not record:
            raise ValueError(f'missing DamageInfo {damage_type}')
        raw = record['raw']
        node = {'kind': 'DamageInfo', 'path': path, 'linkage': linkage,
            'recordType': damage_type, 'group': record['group'], 'row': record['row'],
            'fields': {
                'damage.standard_damage': scalar(raw, 4, 'i32'),
                'damage.durable_damage': scalar(raw, 8, 'i32'),
                'damage.ap_direct': scalar(raw, 12, 'u32'),
                'damage.ap_slight': scalar(raw, 16, 'u32'),
                'damage.ap_large': scalar(raw, 20, 'u32'),
                'damage.ap_extreme': scalar(raw, 24, 'u32'),
                'damage.demolition': scalar(raw, 28, 'u32'),
                'damage.stagger': scalar(raw, 32, 'u32'),
                'damage.push_force': scalar(raw, 36, 'u32'),
            }, 'statuses': []}
        result.append(node)
        for slot, offset in enumerate((44, 52, 60, 68), 1):
            status_type = scalar(raw, offset, 'u32')
            if not status_type:
                continue
            status = statuses.get(status_type)
            if not status:
                raise ValueError(f'missing StatusEffectSettings {status_type}')
            status_path = f'{path}/status:{slot}'
            status_node = {'kind': 'StatusEffectSettings', 'path': status_path,
                'linkage': 'damage_status', 'slot': slot, 'recordType': status_type,
                'group': status['group'], 'row': status['row'],
                'parentDamageType': damage_type, 'parentDamageGroup': record['group'],
                'parentDamageRow': record['row'],
                'fields': {'status.strength': scalar(raw, offset + 4, 'f32'),
                    'status.duration': scalar(status['raw'], 40, 'f32')}}
            result.append(status_node)
            node['statuses'].append(status_path)
        return node

    def add_explosion(explosion_type, path, linkage):
        if not explosion_type:
            return None
        record = explosions.get(explosion_type)
        if not record:
            raise ValueError(f'missing ExplosionSettings {explosion_type}')
        raw = record['raw']
        node = {'kind': 'ExplosionSettings', 'path': path, 'linkage': linkage,
            'recordType': explosion_type, 'group': record['group'], 'row': record['row'],
            'fields': {
                'explosion.inner_radius': scalar(raw, 16, 'f32'),
                'explosion.outer_radius': scalar(raw, 20, 'f32'),
                'explosion.shockwave_radius': scalar(raw, 24, 'f32'),
            }}
        result.append(node)
        damage_type = scalar(raw, 4, 'u32')
        if damage_type:
            node['damage'] = f'{path}/damage'
            add_damage(damage_type, node['damage'], 'explosion_damage')
        shrapnel_count = scalar(raw, 80, 'u32')
        shrapnel_type = scalar(raw, 84, 'u32')
        if shrapnel_type:
            node['shrapnel'] = {'count': shrapnel_count, 'path': f'{path}/shrapnel'}
            add_projectile(shrapnel_type, node['shrapnel']['path'], 'explosion_shrapnel')
        return node

    def add_projectile(projectile_type, path, linkage):
        cycle = (projectile_type, path)
        if cycle in active:
            raise ValueError(f'projectile graph cycle at {path}')
        record = projectiles.get(projectile_type)
        if not record:
            raise ValueError(f'missing ProjectileSettings {projectile_type}')
        active.add(cycle)
        raw = record['raw']
        node = {'kind': 'ProjectileSettings', 'path': path, 'linkage': linkage,
            'recordType': projectile_type, 'group': record['group'], 'row': record['row'],
            'fields': {
                'projectile.pellet_count': scalar(raw, 28, 'u32'),
                'projectile.velocity': scalar(raw, 32, 'f32'),
                'projectile.mass': scalar(raw, 36, 'f32'),
                'projectile.drag': scalar(raw, 40, 'f32'),
                'projectile.gravity': scalar(raw, 44, 'f32'),
            }}
        result.append(node)
        damage_type = scalar(raw, 60, 'u32')
        if damage_type:
            node['damage'] = f'{path}/damage'
            add_damage(damage_type, node['damage'], 'projectile_damage')
        for phase, offset in (('impact', 144), ('expiry', 156)):
            explosion_type = scalar(raw, offset, 'u32')
            if explosion_type:
                target = f'{path}/{phase}'
                node[phase] = target
                add_explosion(explosion_type, target, f'projectile_{phase}')
        active.remove(cycle)
        return node

    for slot, projectile_type in enumerate(root_types, 1):
        add_projectile(projectile_type, f'delivery:{slot}/projectile', 'payload_delivery')
    return result


def build(snapshot=SNAPSHOT, wiki_path=WIKI, named_path=NAMED_REFERENCE):
    wiki = json.loads(Path(wiki_path).read_text(encoding='utf-8'))
    named = named_rows(Path(named_path))
    snapshot_data = snapshot_evidence(Path(snapshot))
    current = snapshot_data['stratagems']
    by_id = {row['id']: row for row in current}
    settings = {kind: {int(key): dict(value, raw=bytes.fromhex(value['raw']))
        for key, value in records.items()}
        for kind, records in snapshot_data['settings'].items()}

    helper_dir = LASER / 'scripts/research'
    sys.path.insert(0, str(helper_dir))
    entity_report = _load_module('stratagem_entity_report', helper_dir / 'entity_report.py')
    probe = sys.modules.get('probe_components') or _load_module(
        'probe_components', helper_dir / 'probe_components.py')
    entities = (FILEDIVER / 'datalibrary/generated_entities.dl_bin').read_bytes()
    typelib = (FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes()
    names = {probe.dl_hash(name): name for name in
        (FILEDIVER / 'hashes/dl_type_names.txt').read_text(encoding='utf-8').splitlines() if name}
    reference_classes = ('ProjectileType', 'ExplosionInfoType', 'DamageInfoType',
        'StatusEffectInfoType', 'BeamInfoType', 'ArcInfoType')
    type_hashes = {probe.dl_hash(name): name for name in reference_classes}

    entries = []
    for imported in wiki['stratagems']:
        historical = named[DEBUG_NAMES[imported['name']]]
        current_row = by_id.get(historical['id'])
        if not current_row:
            raise ValueError('current stratagem identity absent: ' + imported['name'])
        expected_package = f"0x{int(historical['package']):016X}"
        expected_payloads = [f"0x{int(value):016X}" for value in historical['payload']]
        if current_row['package'] != expected_package or current_row['payloads'] != expected_payloads:
            raise ValueError('current stratagem ownership changed: ' + imported['name'])
        payload_reports = []
        for payload in current_row['payloads']:
            report = entity_report.report(entities, typelib, payload, names)
            components = [component for component in report['components'] if component['resolved']]
            payload_reports.append({'payload': payload,
                'components': [{'name': component['name'], 'recordType': component['record_type'],
                    'recordIndex': component['record_index'], 'indexRow': component['index_row'],
                    'instanceOffset': component['instance_offset'],
                    'instanceSize': component['instance_size'],
                    'recordSize': component['record_size'],
                    'recordOffsetInInstance': component['record_offset_in_instance'],
                    'indexCapacity': component['index_capacity'],
                    'header': entities[component['instance_offset']:
                        component['instance_offset'] + 28].hex(),
                    'reviewedScalars': reviewed_scalars(component),
                    'typedReferences': typed_references(component, type_hashes)}
                    for component in components]})
        root_projectiles = []
        for payload_report in payload_reports:
            for component in payload_report['components']:
                if component['name'] == 'BombardmentComponentData':
                    reference = next(item for item in component['typedReferences']
                        if item['referenceClass'] == 'ProjectileType')
                    root_projectiles.extend(reference['values'])
                elif component['name'] == 'EagleComponentData':
                    root_projectiles.extend(value for reference in component['typedReferences']
                        if reference['referenceClass'] == 'ProjectileType'
                        and reference['path'] == [24] for value in reference['values'])
                elif imported['name'] == 'Eagle Strafing Run' \
                        and component['name'] == 'ProjectileWeaponComponentData':
                    root_projectiles.extend(value for reference in component['typedReferences']
                        if reference['referenceClass'] == 'ProjectileType'
                        and reference['path'] == [0] for value in reference['values'])
                elif imported['name'] == 'Orbital Railcannon Strike' \
                        and component['name'] == 'OrbitalAbilityComponentData':
                    root_projectiles.extend(value for reference in component['typedReferences']
                        if reference['referenceClass'] == 'ProjectileType'
                        and reference['path'] == [532] for value in reference['values'])
        graph = primitive_graph(settings['projectile'], settings['damage'],
            settings['explosion'], settings['status'], root_projectiles)
        if imported['name'] == 'Orbital Laser':
            damage_type = next(value for report in payload_reports
                for component in report['components']
                if component['name'] == 'OrbitalAbilityComponentData'
                for reference in component['typedReferences']
                if reference['referenceClass'] == 'DamageInfoType'
                for value in reference['values'])
            laser_record = settings['damage'][damage_type]
            laser_raw = laser_record['raw']
            ability = next(component for report in payload_reports for component in report['components']
                if component['name'] == 'OrbitalAbilityComponentData')
            ability_scalars = ability['reviewedScalars']
            graph.insert(0, {'kind': 'Beam', 'path': 'beam', 'linkage': 'orbital_ability',
                'fields': {'orbital.duration': ability_scalars['460'],
                    'orbital.movement_speed': ability_scalars['468'],
                    'orbital.search_radius': ability_scalars['472'],
                    'orbital.tick_interval': ability_scalars['480']}})
            graph.insert(1, {'kind': 'DamageInfo', 'path': 'beam/damage',
                'linkage': 'orbital_ability_damage', 'recordType': damage_type,
                'group': laser_record['group'], 'row': laser_record['row'],
                'fields': {
                    'damage.standard_damage': scalar(laser_raw, 4, 'i32'),
                    'damage.durable_damage': scalar(laser_raw, 8, 'i32'),
                    'damage.ap_direct': scalar(laser_raw, 12, 'u32'),
                    'damage.ap_slight': scalar(laser_raw, 16, 'u32'),
                    'damage.ap_large': scalar(laser_raw, 20, 'u32'),
                    'damage.ap_extreme': scalar(laser_raw, 24, 'u32'),
                    'damage.demolition': scalar(laser_raw, 28, 'u32'),
                    'damage.stagger': scalar(laser_raw, 32, 'u32'),
                    'damage.push_force': scalar(laser_raw, 36, 'u32')}})
        entries.append({'name': imported['name'], 'family': imported['family'],
            'wiki': imported, 'historicalIdentity': {'debugName': historical['debug_name'],
                'id': historical['id'], 'package': expected_package, 'payloads': expected_payloads},
            'currentRoot': current_row, 'payloadReports': payload_reports,
            'rootProjectiles': root_projectiles, 'nativeGraph': graph,
            'importedBranches': [{key: branch.get(key) for key in
                ('id','name','wikiKind','semanticRoles','parentId','childIds')}
                for branch in imported['attacks']]})
    support_catalog = json.loads((ROOT / 'data/wiki_support_weapons.json').read_text())
    support_roots = []
    for support in support_catalog['weapons']:
        debug_name = SUPPORT_DEBUG_NAMES.get(support['name'])
        if not debug_name:
            support_roots.append({'name': support['name'], 'resolution': 'UNRESOLVED',
                'reason': 'No uniquely correlated call-in definition.'})
            continue
        historical = named[debug_name]
        row = by_id.get(historical['id'])
        if not row:
            raise ValueError('current support stratagem identity absent: ' + support['name'])
        expected_package = f"0x{int(historical['package']):016X}"
        expected_payloads = [f"0x{int(value):016X}" for value in historical['payload']]
        if row['package'] != expected_package or row['payloads'] != expected_payloads:
            raise ValueError('current support stratagem ownership changed: ' + support['name'])
        support_roots.append({'name': support['name'], 'resolution': 'UNIQUE',
            'historicalIdentity': {'debugName': debug_name, 'id': historical['id'],
                'package': expected_package, 'payloads': expected_payloads},
            'currentRoot': row})

    eagle_rearm_historical = named['EAGLE. REARM']
    eagle_rearm = by_id.get(eagle_rearm_historical['id'])
    if not eagle_rearm or eagle_rearm['package'] != '0x0000000000000000' \
            or eagle_rearm['payloads']:
        raise ValueError('current Eagle rearm definition changed')
    return {'schemaVersion': 1, 'source': {'wikiCommit':
        '41f01f9b2ca2ea2ca2b9f3adde7c75663582a44a', 'mode': 'snapshot',
        'snapshot': Path(snapshot).name, 'writes': 0, 'protectionChanges': 0,
        'fixtureFallback': 'disabled'}, 'systemRoots': {'eagleRearm': {
            'historicalIdentity': {'debugName': eagle_rearm_historical['debug_name'],
                'id': eagle_rearm_historical['id']}, 'currentRoot': eagle_rearm}},
        'stratagems': entries, 'supportRoots': support_roots}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--wiki', type=Path, default=WIKI)
    parser.add_argument('--named-reference', type=Path, default=NAMED_REFERENCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = build(args.snapshot, args.wiki, args.named_reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'stratagems': len(report['stratagems']),
        'payloads': sum(len(item['payloadReports']) for item in report['stratagems']),
        'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}, indent=2))


if __name__ == '__main__':
    main()
