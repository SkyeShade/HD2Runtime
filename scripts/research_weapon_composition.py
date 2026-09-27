"""Build the four player-weapon composition capability graphs from an HD2 snapshot.

The scan is deliberately bounded to the 80 reviewed player weapon resources, five
weapon component types, and their already-resolved projectile records.  It never
constructs a writer or changes page protection.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sdk'))
from tools.lua_runner import execute

SNAPSHOT = Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
AUTHORING = ROOT / 'schemas/player_weapon_authoring_catalog.json'
AMMO = ROOT / 'schemas/player_weapon_ammo_catalog.json'
RAW = ROOT / 'build/weapon-composition-raw.json'
OUTPUTS = {
    'magazine': ROOT / 'sdk/PlayerWeaponMagazineOptionGraph.json',
    'projectile': ROOT / 'sdk/PlayerWeaponProjectileReferenceGraph.json',
    'fire_mode': ROOT / 'sdk/PlayerWeaponFireModeGraph.json',
    'terminal': ROOT / 'sdk/PlayerWeaponTerminalActionGraph.json',
}
COMPOSITION_CATALOG = ROOT / 'schemas/player_weapon_composition_catalog.json'


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in value.items()) + '}'
    if isinstance(value, list):
        return '{' + ','.join(lua(v) for v in value) + '}'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def module_sources():
    result = {}
    for folder in ('api', 'core', 'runtime', 'schemas', 'domains', 'primary_mapper'):
        for path in sorted((ROOT / folder).glob('*.lua')):
            result['hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()] = path.read_text()
    return result


def scan(snapshot=SNAPSHOT):
    source = json.loads(AUTHORING.read_text())
    requested = []
    for weapon in source['weapons']:
        candidate = source['candidates'][weapon['resources'][0]]
        attacks = []
        for index, attack in enumerate(candidate.get('attacks') or []):
            if attack.get('kind') == 'Projectile':
                attacks.append({'role': attack.get('role') or ('primary' if index == 0 else 'alternate'),
                    'projectileType': attack['projectileType']})
        requested.append({'name': weapon['name'], 'resource': weapon['resources'][0], 'attacks': attacks})
    sources = module_sources()
    preload = '\n'.join("package.preload[" + lua(name) + "]=function(...) return assert(loadstring("
        + lua(body) + ',' + lua(name) + "))(...) end" for name, body in sources.items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + lua(str(Path(snapshot).resolve())) + r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local reader=Reader.new(source)
local roots=discover.locate(source,reader,profile,{entity=true,projectile=true,damage=true,
 explosion=true,status='optional'})
local component_names={'ProjectileWeaponComponentData','WeaponDataComponentData',
 'WeaponMagazineComponentData','WeaponRoundsComponentData','WeaponCustomizationComponentData'}
local catalog=entities.capture(reader,roots.entity,profile,component_names)
local requested=''' + lua(requested) + r'''
local by_resource={}
for _,candidate in ipairs(catalog.candidates)do by_resource[candidate.resourceHash]=candidate end
local function hex(bytes)
 local out={};for index=1,#bytes do out[index]=string.format('%02x',bytes:byte(index))end
 return table.concat(out)
end
local result={mode='snapshot',fingerprints={exe=source.module_hash(source.module(nil)),
 dll=source.module_hash(source.module('game.dll'))},weapons={},writes=0,protectionChanges=0,
 fixtureFallback='disabled'}
for _,item in ipairs(requested)do
 local candidate=assert(by_resource[item.resource],'reviewed player resource missing: '..item.resource)
 local output={name=item.name,resourceHash=item.resource,ownership=candidate.ownership,
  components={},projectiles={}}
 for _,name in ipairs(component_names)do
  if candidate.ownership[name]then
   local record=catalog.record(candidate,name)
   output.components[name]={identity=record.identity,bytes=hex(record.bytes),length=#record.bytes}
  end
 end
 for _,attack in ipairs(item.attacks)do
  local projectile=assert(roots.projectile.records[attack.projectileType],
   'reviewed projectile absent: '..attack.projectileType)
  local damage_type=b.u32(projectile.bytes,60)
  local status_count=0
  local damage=roots.damage.records[damage_type]
  if damage then
   for index=0,3 do if b.u32(damage.bytes,44+index*8)==0 then break end;status_count=status_count+1 end
  end
  local references={}
  for offset=128,176,4 do
   local value=b.u32(projectile.bytes,offset)
   references[#references+1]={offset=offset,value=value,
    explosionRecord=value~=0 and roots.explosion.records[value]~=nil or false}
  end
  output.projectiles[#output.projectiles+1]={role=attack.role,projectileType=attack.projectileType,
   settings={group=projectile.group,row=projectile.row,recordType=projectile.kind,
    settingsType=projectile.settings_type},damageType=damage_type,statusCount=status_count,
   impactExplosionType=b.u32(projectile.bytes,144),expiryExplosionType=b.u32(projectile.bytes,156),
   references=references,bytes=hex(projectile.bytes),length=#projectile.bytes}
 end
 result.weapons[#result.weapons+1]=output
end
reader.stage='runtime/reader:stable_reread';reader.verify();source.close()
return result
end)
local ok,value
repeat ok,value=coroutine.resume(worker) until not ok or coroutine.status(worker)=='dead'
assert(ok,value)
return json.encode(value)
'''
    result = json.loads(execute(program.encode()))
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(result, indent=2) + '\n')
    return result


def _find_all(data: bytes, needle: bytes):
    result = []
    at = data.find(needle)
    while at >= 0:
        result.append(at)
        at = data.find(needle, at + 1)
    return result


def analyze(raw):
    authoring = json.loads(AUTHORING.read_text())
    ammo = json.loads(AMMO.read_text())
    ammo_by_name = {item['name']: item for item in ammo['weapons']}
    author_by_name = {item['name']: item for item in authoring['weapons']}
    candidate_by_name = {item['name']: authoring['candidates'][item['resources'][0]]
        for item in authoring['weapons']}
    raw_by_name = {item['name']: item for item in raw['weapons']}
    option_catalog = ammo['nativeMagazineOptions']
    safety = {'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled',
        'snapshotOnly': True}
    common = {'schemaVersion': 1, 'sourceSnapshot': SNAPSHOT.name,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'gameFingerprints': raw['fingerprints'], 'catalogWeapons': 80, 'safety': safety}

    magazine_weapons = []
    option_occurrences = Counter()
    for name in sorted(author_by_name):
        info = ammo_by_name[name]
        custom = raw_by_name[name]['components'].get('WeaponCustomizationComponentData')
        custom_bytes = bytes.fromhex(custom['bytes']) if custom else b''
        seen = []
        for option in option_catalog:
            option_id = int(option['optionId'], 16)
            id_offsets = _find_all(custom_bytes, struct.pack('<I', option_id))
            add_path = int(option['addPath'], 16)
            path_offsets = _find_all(custom_bytes, struct.pack('<Q', add_path))
            if id_offsets or path_offsets:
                option_occurrences[option['optionId']] += 1
                seen.append({'optionId': option['optionId'], 'name': option['name'],
                    'addPath': option['addPath'], 'optionIdOffsets': id_offsets,
                    'addPathOffsets': path_offsets})
        default = info.get('defaultMagazineOption')
        default_entry = None
        if default:
            observed_default = next((x for x in seen if x['optionId'] == default['optionId']), None)
            default_entry = {**default, 'default': True, 'allowed': True,
                'optionIdentityProven': observed_default is not None,
                'allowedRelationshipProven': True,
                'ammoValueOwnerProven': False, 'writable': False,
                'backingOwner': 'WeaponCustomizationComponentData.DefaultCustomizations[Magazine]',
                'defaultEntryOffset': (observed_default['optionIdOffsets'][0] - 4
                    if observed_default and observed_default['optionIdOffsets'] else None),
                'reason': 'Default option identity is native, but no option-owned ammo override record is structurally linked.'}
        magazine_weapons.append({'weapon': name, 'resources': info['resources'],
            'ordinaryWritesBlocked': info['ordinaryWritesBlocked'],
            'backingDomain': info['backingDomain'], 'simpleMagazineApi': default is None,
            'defaultOption': default_entry, 'observedCustomizationOptions': seen,
            'alternateOptions': info['alternateMagazineOptions'],
            'effectiveCapacity': info['effectiveCapacity'], 'fields': info['fields']})
    magazine = {**common, 'feature': 'magazine_option_graph',
        'summary': {'weapons': 80, 'nativeOptionIdentities': len(option_catalog),
            'weaponsWithNativeDefaultOption': sum(w['defaultOption'] is not None for w in magazine_weapons),
            'defaultRelationshipsProven': sum(w['defaultOption'] is not None and
                w['defaultOption']['optionIdentityProven'] for w in magazine_weapons),
            'perOptionAmmoOwnersProven': 0, 'writableOptionFields': 0,
            'simpleMagazineWeapons': ammo['summary']['directMagazineWeapons'],
            'roundsFeedWeapons': ammo['summary']['roundsFeedWeapons']},
        'findings': {'defaultSlot': {'component': 'WeaponCustomizationComponentData',
            'path': 'DefaultCustomizations[] entry where slot == Magazine', 'slotTag': 5,
            'listOffset': 0, 'entryStride': 8, 'slotOffset': 0, 'optionIdOffset': 4,
            'terminatorSlot': 0},
            'allowedOptions': 'No reviewed per-weapon allowed-option list was found in the captured component record.',
            'overrideOwnership': 'No option-owned ammo override record is linked by the captured component graph.'},
        'nativeMagazineOptions': option_catalog, 'weapons': magazine_weapons}

    projectile_weapons = []
    writable_attacks = 0
    plain_sources = []
    terminal_weapons = []
    explosion_offset_hits = Counter()
    neighbor_nonzero = Counter()
    for name in sorted(author_by_name):
        identity = author_by_name[name]
        candidate = candidate_by_name[name]
        raw_weapon = raw_by_name[name]
        attacks = []
        terminal_attacks = []
        raw_projectiles = {item['role']: item for item in raw_weapon['projectiles']}
        projectile_attacks = [item for item in candidate.get('attacks') or [] if item.get('kind') == 'Projectile']
        for position, attack in enumerate(projectile_attacks):
            role = attack.get('role') or ('primary' if position == 0 else 'alternate')
            record = raw_projectiles[role]
            impact = record['impactExplosionType']
            expiry = record['expiryExplosionType']
            status = record['statusCount'] > 0
            explosive = impact != 0 or expiry != 0
            compatibility = ('explosive_status' if explosive and status else
                'explosive' if explosive else 'status_bearing' if status else 'conventional_plain')
            if 'WeaponRoundsComponentData' in candidate['ownership']:
                component = 'WeaponRoundsComponentData'
                offset = 68 if role in ('alternate', 'feed_alternate') else 64
            elif 'ProjectileWeaponComponentData' in candidate['ownership']:
                component = 'ProjectileWeaponComponentData'; offset = 0
            else:
                component = None; offset = None
            owner = candidate['ownership'].get(component) if component else None
            unique_identity = identity['resolution'] == 'UNIQUE'
            target_owned = bool(owner and owner['uniqueOwner'] and owner['ownerCount'] == 1)
            writable = unique_identity and target_owned and compatibility == 'conventional_plain'
            if writable:
                writable_attacks += 1
            item = {'role': role, 'projectileType': attack['projectileType'],
                'projectileSettings': attack['projectileSettings'], 'compatibilityClass': compatibility,
                'targetBacking': ({'component': component, 'offset': offset, 'width': 4,
                    'storage': 'u32', 'recordIndex': owner['recordIndex'],
                    'indexRow': owner['indexRow'], 'ownerCount': owner['ownerCount'],
                    'uniqueOwner': owner['uniqueOwner']} if owner else None),
                'sourceIdentityResolvable': unique_identity, 'targetOwnershipProven': target_owned,
                'writableReferenceSwap': writable,
                'reason': None if writable else ('ambiguous weapon identity' if not unique_identity else
                    'weapon-local projectile selector is absent or shared' if not target_owned else
                    'only conventional_plain to conventional_plain swaps are approved')}
            attacks.append(item)
            if unique_identity and compatibility == 'conventional_plain':
                plain_sources.append({'weapon': name, 'role': role, 'projectileType': attack['projectileType']})
            actions = []
            for phase, value, offset in (('impact', impact, 144), ('expiry', expiry, 156)):
                linked = next((x for x in record['references'] if x['offset'] == offset), None)
                if linked and linked['explosionRecord']:
                    explosion_offset_hits[offset] += 1
                actions.append({'phase': phase, 'offset': offset, 'width': 4, 'storage': 'u32',
                    'referenceType': value, 'actionKind': 'explosion' if value else 'none',
                    'linkedExplosionRecord': bool(linked and linked['explosionRecord']),
                    'readable': True, 'writable': False,
                    'reason': 'Reference layout is proven read-only; guarded terminal-action replacement awaits native consumer confirmation.'})
            for ref in record['references']:
                if ref['value']:
                    neighbor_nonzero[ref['offset']] += 1
            terminal_attacks.append({'role': role, 'projectileType': attack['projectileType'],
                'projectileSettings': attack['projectileSettings'], 'actions': actions})
        projectile_weapons.append({'weapon': name, 'resources': identity['resources'],
            'resolution': identity['resolution'], 'implementationFamilies': candidate['implementationFamilies'],
            'attacks': attacks})
        terminal_weapons.append({'weapon': name, 'resources': identity['resources'],
            'resolution': identity['resolution'], 'attacks': terminal_attacks})
    projectile = {**common, 'feature': 'projectile_reference_graph',
        'summary': {'weapons': 80, 'weaponsWithProjectileAttack': sum(bool(w['attacks']) for w in projectile_weapons),
            'projectileAttacks': sum(len(w['attacks']) for w in projectile_weapons),
            'writableTargetAttacks': writable_attacks, 'compatibleSourceAttacks': len(plain_sources)},
        'guardPolicy': {'operationKind': 'typed_reference_replacement',
            'allowed': 'conventional_plain -> conventional_plain',
            'sourceSettingsMutated': False, 'expectedReferenceRequired': True,
            'sourceIdentityMustResolveUniquely': True,
            'sharedTargetPolicy': 'fail_closed; no shared target selector is promoted in this pass'},
        'compatibleSources': plain_sources, 'weapons': projectile_weapons}

    fire_groups = defaultdict(list)
    fire_weapons = []
    for name in sorted(author_by_name):
        identity = author_by_name[name]; candidate = candidate_by_name[name]
        value = candidate['resolvedFields'].get('primary_fire_mode')
        if value is not None:
            fire_groups[str(value)].append(name)
        owner = candidate['ownership'].get('WeaponDataComponentData')
        fire_weapons.append({'weapon': name, 'resources': identity['resources'],
            'implementationFamilies': candidate['implementationFamilies'],
            'primaryFireModeNativeValue': value,
            'backing': ({'component': 'WeaponDataComponentData', 'offset': 144, 'width': 4,
                'storage': 'u32', 'recordIndex': owner['recordIndex'], 'indexRow': owner['indexRow']}
                if owner and value is not None else None),
            'allowedModes': None, 'defaultModeSemantics': 'unresolved',
            'selectedRuntimeMode': None, 'writable': False,
            'reason': 'One schema-labelled native value is readable; allowed-mode collection and enum semantics are not proven.'})
    fire_mode = {**common, 'feature': 'fire_mode_graph',
        'summary': {'weapons': 80, 'nativePrimaryValueReadable': sum(w['primaryFireModeNativeValue'] is not None for w in fire_weapons),
            'allowedModeListsProven': 0, 'writableWeapons': 0},
        'nativeValueGroups': dict(sorted(fire_groups.items())),
        'findings': {'primaryValue': {'component': 'WeaponDataComponentData', 'offset': 144,
            'storage': 'u32'}, 'rateSelector': 'Separate from fire-mode selection; no player-weapon rate selector graph was proven.',
            'jar5FullAuto': 'Blocked: JAR-5 native value is readable, but Full Auto compatibility and allowed-mode ownership are not proven.'},
        'weapons': fire_weapons}

    terminal = {**common, 'feature': 'projectile_terminal_action_graph',
        'summary': {'weapons': 80, 'projectileAttacks': sum(len(w['attacks']) for w in terminal_weapons),
            'readableActions': sum(2 * len(w['attacks']) for w in terminal_weapons),
            'writableActions': 0, 'impactExplosionLinks': explosion_offset_hits[144],
            'expiryExplosionLinks': explosion_offset_hits[156]},
        'layout': {'record': 'ProjectileSettings', 'recordSize': 272,
            'impact': {'offset': 144, 'schemaLabel': 'ProjectileInfo.ExplosionType'},
            'expiry': {'offset': 156, 'schemaLabel': 'lifetime-end explosion candidate'}},
        'neighborReferenceEvidence': [{'offset': offset, 'nonzeroRecords': neighbor_nonzero[offset],
            'linkedExplosionRecords': explosion_offset_hits[offset]} for offset in range(128, 177, 4)],
        'findings': {'impact': 'Schema-labelled ExplosionType and structurally linked ExplosionSettings records.',
            'expiry': 'Current records link ExplosionSettings where nonzero, but the native consumer label remains incomplete.',
            'otherActions': 'Neighboring nonzero scalars are not promoted without typed ownership or consumer evidence.'},
        'weapons': terminal_weapons}
    return {'magazine': magazine, 'projectile': projectile, 'fire_mode': fire_mode, 'terminal': terminal}


def write(reports):
    for key, path in OUTPUTS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports[key], indent=2) + '\n')
    magazines = {item['weapon']: item for item in reports['magazine']['weapons']}
    projectiles = {item['weapon']: item for item in reports['projectile']['weapons']}
    fire_modes = {item['weapon']: item for item in reports['fire_mode']['weapons']}
    terminals = {item['weapon']: item for item in reports['terminal']['weapons']}
    catalog = {'schemaVersion': 1, 'sourceSnapshot': SNAPSHOT.name,
        'hd2RuntimeVersion': reports['projectile']['hd2RuntimeVersion'],
        'gameFingerprints': reports['projectile']['gameFingerprints'],
        'summary': {key: value['summary'] for key, value in reports.items()}, 'weapons': {}}
    for name in sorted(magazines):
        terminal_by_role = {item['role']: item['actions'] for item in terminals[name]['attacks']}
        catalog['weapons'][name] = {
            'magazine': {'simpleApi': magazines[name]['simpleMagazineApi'],
                'defaultOption': magazines[name]['defaultOption'],
                'observedOptions': magazines[name]['observedCustomizationOptions']},
            'fireMode': {'nativeValue': fire_modes[name]['primaryFireModeNativeValue'],
                'backing': fire_modes[name]['backing'], 'writable': False},
            'attacks': [{**attack,
                'aliases': (['primary'] if index == 0 else ['alternate']),
                'terminalActions': terminal_by_role.get(attack['role'], [])}
                for index, attack in enumerate(projectiles[name]['attacks'])]}
    COMPOSITION_CATALOG.write_text(json.dumps(catalog, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', nargs='?', type=Path, default=SNAPSHOT)
    parser.add_argument('--raw', type=Path, help='Analyze an existing raw scan instead of opening a snapshot')
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text()) if args.raw else scan(args.snapshot)
    reports = analyze(raw); write(reports)
    print(json.dumps({key: value['summary'] for key, value in reports.items()}, indent=2))


if __name__ == '__main__':
    main()
