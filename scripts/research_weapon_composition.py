"""Build the four player-weapon composition capability graphs from an HD2 snapshot.

The scan is deliberately bounded to the 80 reviewed player weapon resources, five
weapon component types, and their already-resolved projectile records.  It never
constructs a writer or changes page protection.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)
import package_residency_evidence  # noqa: E402
import apply_projectile_residency  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sdk'))
from tools.lua_runner import execute

SNAPSHOT = build_profile.SNAPSHOT
AUTHORING = ROOT / 'schemas/player_weapon_authoring_catalog.json'
AMMO = ROOT / 'schemas/player_weapon_ammo_catalog.json'
ATTACHMENTS_SOURCE = ROOT.parent / 'HD2WikiImporter/output/wiki_primary_weapon_attachments.json'
ATTACHMENTS_CATALOG = ROOT / 'schemas/player_weapon_attachment_catalog.json'
PLAYER_CATALOG = ROOT / 'data/wiki_player_weapons.json'
RAW = ROOT / 'build/weapon-composition-raw.json'
OUTPUTS = {
    'magazine': ROOT / 'sdk/AttachmentOptionCapabilities.json',
    'projectile': ROOT / 'sdk/ProjectileCompositionCapabilities.json',
    'fire_mode': ROOT / 'sdk/PlayerWeaponFireModeGraph.json',
    'terminal': ROOT / 'sdk/PlayerWeaponTerminalActionGraph.json',
    'explosion': ROOT / 'sdk/ExplosionAuthoringCapabilities.json',
    'heat': ROOT / 'sdk/PlayerWeaponHeatCapabilities.json',
}
COMPOSITION_CATALOG = ROOT / 'schemas/player_weapon_composition_catalog.json'
HEAT_RESEARCH = ROOT / 'research/player-weapon-heat-F5FEE03DCFDB.json'


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
 'WeaponMagazineComponentData','WeaponRoundsComponentData','WeaponCustomizationComponentData',
 'WeaponHeatComponentData'}
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
 fixtureFallback='disabled',customizationCorpus={}}
local customization_records={}
for _,candidate in ipairs(catalog.candidates)do
 local identity=candidate.ownership.WeaponCustomizationComponentData
 if identity and candidate.entityRow and#candidate.diagnostics==0
    and not customization_records[identity.recordIndex]then
  local record=catalog.record(candidate,'WeaponCustomizationComponentData')
  local item={resourceHash=candidate.resourceHash,identity=identity,bytes=hex(record.bytes)}
  customization_records[identity.recordIndex]=item
  result.customizationCorpus[#result.customizationCorpus+1]=item
 end
end
table.sort(result.customizationCorpus,function(a,c)return a.identity.recordIndex<c.identity.recordIndex end)
local projectile_consumers={}
local function add_projectile_consumer(projectile_type,candidate,component,offset)
 if projectile_type==0 then return end
 projectile_consumers[projectile_type]=projectile_consumers[projectile_type]or{}
 projectile_consumers[projectile_type][#projectile_consumers[projectile_type]+1]={
  resourceHash=candidate.resourceHash,component=component,offset=offset}
end
for _,candidate in ipairs(catalog.candidates)do
 if candidate.entityRow and#candidate.diagnostics==0 then
  if candidate.ownership.ProjectileWeaponComponentData then
   local ok,record=pcall(catalog.record,candidate,'ProjectileWeaponComponentData')
   if ok then add_projectile_consumer(b.u32(record.bytes,0),candidate,
    'ProjectileWeaponComponentData',0)end
  end
  if candidate.ownership.WeaponRoundsComponentData then
   local ok,record=pcall(catalog.record,candidate,'WeaponRoundsComponentData')
   if ok then
    add_projectile_consumer(b.u32(record.bytes,64),candidate,'WeaponRoundsComponentData',64)
    add_projectile_consumer(b.u32(record.bytes,68),candidate,'WeaponRoundsComponentData',68)
   end
  end
 end
end
local explosion_consumers={}
local explosion_damage_consumers={}
for explosion_type,explosion in pairs(roots.explosion.records)do
 local damage_type=b.u32(explosion.bytes,4)
 if damage_type~=0 then
  explosion_damage_consumers[damage_type]=explosion_damage_consumers[damage_type]or{}
  explosion_damage_consumers[damage_type][#explosion_damage_consumers[damage_type]+1]=explosion_type
 end
end
for projectile_type,projectile in pairs(roots.projectile.records)do
 for _,offset in ipairs({144,156})do
  local explosion_type=b.u32(projectile.bytes,offset)
  if explosion_type~=0 then
   explosion_consumers[explosion_type]=explosion_consumers[explosion_type]or{}
   explosion_consumers[explosion_type][#explosion_consumers[explosion_type]+1]={
    projectileType=projectile_type,phase=offset==144 and'impact'or'expiry'}
  end
 end
end
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
  local explosions={}
  local seen_explosions={}
  for _,terminal in ipairs({{phase='impact',offset=144},{phase='expiry',offset=156}})do
   local explosion_type=b.u32(projectile.bytes,terminal.offset)
   if explosion_type~=0 and not seen_explosions[explosion_type]then
    seen_explosions[explosion_type]=true
    local explosion=assert(roots.explosion.records[explosion_type],
     'linked ExplosionSettings absent: '..explosion_type)
    local damage_type=b.u32(explosion.bytes,4)
    local damage=assert(roots.damage.records[damage_type],
     'linked explosion DamageInfo absent: '..damage_type)
    local projectile_refs={}
    for offset=0,#explosion.bytes-4,4 do
     local value=b.u32(explosion.bytes,offset)
     local linked=value~=0 and roots.projectile.records[value]or nil
     if linked then projectile_refs[#projectile_refs+1]={offset=offset,projectileType=value,
      settings={group=linked.group,row=linked.row,recordType=linked.kind,
       settingsType=linked.settings_type},bytes=hex(linked.bytes)}end
    end
    explosions[#explosions+1]={explosionType=explosion_type,
     settings={group=explosion.group,row=explosion.row,recordType=explosion.kind,
      settingsType=explosion.settings_type},bytes=hex(explosion.bytes),length=#explosion.bytes,
     damageType=damage_type,damage={group=damage.group,row=damage.row,recordType=damage.kind,
      settingsType=damage.settings_type,bytes=hex(damage.bytes),length=#damage.bytes,
      consumers=explosion_damage_consumers[damage_type]or{}},
     projectileReferences=projectile_refs,consumers=explosion_consumers[explosion_type]or{}}
   end
  end
  output.projectiles[#output.projectiles+1]={role=attack.role,projectileType=attack.projectileType,
   settings={group=projectile.group,row=projectile.row,recordType=projectile.kind,
    settingsType=projectile.settings_type},damageType=damage_type,statusCount=status_count,
   impactExplosionType=b.u32(projectile.bytes,144),expiryExplosionType=b.u32(projectile.bytes,156),
   references=references,explosions=explosions,consumers=projectile_consumers[attack.projectileType]or{},
   bytes=hex(projectile.bytes),length=#projectile.bytes}
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


def _u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def _i32(data, offset):
    return struct.unpack_from('<i', data, offset)[0]


WARMUP_REASON = ('Derived: heat.firing_charge / heat.charge_gain_per_second (the charge built before the first shot, '
    'at the charge gained per second); edit heat.firing_charge or heat.charge_gain_per_second.')
OVERHEAT_COOLDOWN_REASON = ('No proven member of its own: after an overheat the weapon cools from heat.capacity at '
    'heat.cool_per_second (before the native cold / hot multipliers, heat.cool_per_second_cold / _hot); edit '
    'heat.capacity or heat.cool_per_second.')


def warmup_seconds(charge, gain):
    """Seconds of charge before the first shot: firing charge / charge gain per second (0 without a charge)."""
    if charge <= 0:
        return 0.0
    return charge / gain if gain > 0 else None


def _f32(data, offset):
    return struct.unpack_from('<f', data, offset)[0]


def _attachment_effects(option):
    result = {}
    for key, item in option.get('effects', {}).items():
        if key in ('zoomValues', 'magnificationValues'):
            result[key] = [value['value'] for value in item]
        elif isinstance(item, dict) and 'value' in item:
            result[key] = item['value']
    return result


def _wiki_heat_values(weapon):
    fields = next((section['fields'] for section in weapon.get('rawSections', [])
        if section['name'] == 'Heat Data'), [])
    result = {}
    for item in fields:
        numbers = [float(value) for value in re.findall(r'-?\d+(?:\.\d+)?', item['value'])]
        result[item['label']] = numbers
    stats = weapon.get('weaponStats') or {}
    for key in ('spareMagazines', 'startingMagazines', 'magsFromSupply', 'magsFromAmmoBox'):
        result[key] = (stats.get(key) or {}).get('value')
    return result


def _default_attachment(default, options):
    if not default:
        return None
    expected = default.get('values') or {}
    aliases = {'capacity': 'capacity', 'startingMagazines': 'startingMagazines',
        'spareMagazines': 'maxMagazines'}
    matches = []
    for option in options:
        correlation = option.get('magazineCorrelation') or {}
        compared = 0
        for native, wiki in aliases.items():
            if expected.get(native) is not None and correlation.get(wiki) is not None:
                compared += 1
                if expected[native] != correlation[wiki]:
                    break
        else:
            if compared >= 2:
                matches.append(option)
    return matches[0] if len(matches) == 1 else None


def analyze(raw):
    authoring = json.loads(AUTHORING.read_text())
    ammo = json.loads(AMMO.read_text())
    attachment_source = json.loads(ATTACHMENTS_SOURCE.read_text())
    player_source = json.loads(PLAYER_CATALOG.read_text())
    ammo_by_name = {item['name']: item for item in ammo['weapons']}
    author_by_name = {item['name']: item for item in authoring['weapons']}
    candidate_by_name = {item['name']: authoring['candidates'][item['resources'][0]]
        for item in authoring['weapons']}
    raw_by_name = {item['name']: item for item in raw['weapons']}
    option_catalog = ammo['nativeMagazineOptions']
    customization_corpus = [bytes.fromhex(item['bytes'])
        for item in raw.get('customizationCorpus', [])]
    corpus_evidence = []
    for option in option_catalog:
        option_needle = struct.pack('<I', int(option['optionId'], 16))
        path_needle = struct.pack('<Q', int(option['addPath'], 16))
        corpus_evidence.append({'optionId': option['optionId'], 'name': option['name'],
            'addPath': option['addPath'],
            'recordsWithOptionId': sum(option_needle in body for body in customization_corpus),
            'optionIdOccurrences': sum(len(_find_all(body, option_needle)) for body in customization_corpus),
            'recordsWithAddPath': sum(path_needle in body for body in customization_corpus),
            'addPathOccurrences': sum(len(_find_all(body, path_needle)) for body in customization_corpus)})
    safety = {'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled',
        'snapshotOnly': True}
    common = {'schemaVersion': 1, 'sourceSnapshot': SNAPSHOT.name,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(),
        'gameFingerprints': raw['fingerprints'], 'catalogWeapons': 80, 'safety': safety}

    imported_attachments = {item['name']: item for item in attachment_source['weapons']}
    imported_weapons = {item['name']: item for item in player_source['weapons']}
    magazine_weapons = []
    option_occurrences = Counter()
    for name in sorted(author_by_name):
        info = ammo_by_name[name]
        imported = imported_attachments.get(name, {'optionsByCategory': {}, 'attachmentCount': 0})
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
        magazine_options = imported.get('optionsByCategory', {}).get('Magazine', [])
        if not default and magazine_options:
            native_defaults = [item for item in seen if item['optionIdOffsets'] and
                all(offset >= 4 and _u32(custom_bytes, offset - 4) == 5
                    for offset in item['optionIdOffsets'])]
            if len(native_defaults) == 1:
                observed = native_defaults[0]
                default = {'optionId': observed['optionId'], 'addPath': observed['addPath'],
                    'name': observed['name'], 'values': {}}
        matched_default = _default_attachment(default, magazine_options)
        if default and matched_default is None and 'standard' in default['name'].lower():
            standard = [option for option in magazine_options if 'standard' in option['name'].lower()]
            if len(standard) == 1:
                matched_default = standard[0]
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
        categories = []
        for category, options in sorted(imported.get('optionsByCategory', {}).items()):
            rendered = []
            for option in options:
                is_default = matched_default is option
                rendered.append({'category': category, 'name': option['name'],
                    'default': is_default, 'catalogAllowed': True,
                    'nativeAllowedRelationshipProven': is_default and default_entry is not None,
                    'optionIdentityProven': is_default and default_entry is not None,
                    'nativeOption': ({'optionId': default_entry['optionId'],
                        'addPath': default_entry['addPath'], 'name': default_entry['name']}
                        if is_default and default_entry else None),
                    'effects': _attachment_effects(option),
                    'nativeEffectOwner': None, 'sharedConsumers': [], 'writable': False,
                    'reason': ('Default selection identity is native, but effect override ownership is unresolved.'
                        if is_default and default_entry else
                        'Importer proves catalog compatibility only; native option identity and effect owner are unresolved.')})
            categories.append({'category': category, 'options': rendered})
        magazine_weapons.append({'weapon': name, 'resources': info['resources'],
            'ordinaryWritesBlocked': info['ordinaryWritesBlocked'],
            'backingDomain': info['backingDomain'], 'simpleMagazineApi': default is None,
            'defaultOption': default_entry, 'observedCustomizationOptions': seen,
            'alternateOptions': info['alternateMagazineOptions'],
            'effectiveCapacity': info['effectiveCapacity'], 'fields': info['fields'],
            'attachmentCount': imported.get('attachmentCount', 0), 'categories': categories})
    mapped_rows = sum(item['attachmentCount'] for item in magazine_weapons)
    native_magazine_options = sum(1 for weapon in magazine_weapons for category in weapon['categories']
        if category['category'] == 'Magazine' for option in category['options']
        if option['optionIdentityProven'])
    magazine = {**common, 'feature': 'attachment_option_capabilities',
        'importer': {'commit': '6c60b215377a40a004b54c011dc26dc674a1abfe',
            'importedAt': attachment_source['importedAt'], 'source': attachment_source['source']},
        'summary': {'weapons': 80, 'primaryWeaponsWithAttachments': 37,
            'attachmentOptionsMapped': mapped_rows, 'attachmentOptionsTotal': 419,
            'magazineOptionsMapped': 36, 'magazineOptionsTotal': 36,
            'magazineOptionsWithNativeIdentity': native_magazine_options,
            'weaponsWithWritablePerOptionFields': 0,
            'opticsMapped': 195, 'underbarrelMapped': 117, 'muzzleMapped': 71,
            'nativeOptionIdentities': len(option_catalog),
            'customizationRecordsScanned': len(customization_corpus),
            'nativeOptionIdsObservedInCorpus': sum(item['optionIdOccurrences'] > 0
                for item in corpus_evidence),
            'nativeAddPathsObservedInCorpus': sum(item['addPathOccurrences'] > 0
                for item in corpus_evidence),
            'weaponsWithNativeDefaultOption': sum(w['defaultOption'] is not None for w in magazine_weapons),
            'defaultRelationshipsProven': sum(w['defaultOption'] is not None and
                w['defaultOption']['optionIdentityProven'] for w in magazine_weapons),
            'perOptionAmmoOwnersProven': 0, 'writableOptionFields': 0,
            'writableAttachmentSelections': 0, 'alternateAllowedRelationshipsProven': 0,
            'completeCustomizationRecordsCompared': sum(
                'WeaponCustomizationComponentData' in raw_by_name[name]['components']
                for name in raw_by_name),
            'simpleMagazineWeapons': ammo['summary']['directMagazineWeapons'],
            'roundsFeedWeapons': ammo['summary']['roundsFeedWeapons']},
        'findings': {'defaultSlot': {'component': 'WeaponCustomizationComponentData',
            'path': 'DefaultCustomizations[] entry where slot == Magazine', 'slotTag': 5,
            'listOffset': 0, 'entryStride': 8, 'slotOffset': 0, 'optionIdOffset': 4,
            'terminatorSlot': 0},
            'allowedOptions': 'The importer supplies catalog relationships; across the complete native customization table, reviewed weapon records contain their selected default identity but no alternate per-weapon allowed-option list.',
            'overrideOwnership': 'No option-owned attachment effect/ammo override record is linked by the captured component graph.',
            'effectTupleSearch': 'All normalized tuples were compared with the complete captured customization components; scalar correlation without a native option-to-owner reference was rejected.',
            'writePolicy': 'Correlation never promotes a write without native option identity, effect owner, and scope.'},
        'nativeMagazineOptions': option_catalog,
        'nativeOptionCorpusEvidence': corpus_evidence, 'weapons': magazine_weapons}

    heat_weapons = []
    heat_shared = defaultdict(list)
    for name in sorted(author_by_name):
        identity = author_by_name[name]
        raw_component = raw_by_name[name]['components'].get('WeaponHeatComponentData')
        if not raw_component:
            heat_weapons.append({'weapon': name, 'resources': identity['resources'],
                'heatMechanismPresent': False, 'heatsinkMechanismPresent': False,
                'fields': [], 'reason': 'WeaponHeatComponentData is absent from the weapon root.'})
            continue
        body = bytes.fromhex(raw_component['bytes'])
        owner = raw_component['identity']
        heat_shared[owner['recordIndex']].append(name)
        wiki_heat = _wiki_heat_values(imported_weapons[name])
        cooling = wiki_heat.get('Cool Per Sec') or []
        expected = {
            'heat.capacity': (wiki_heat.get('Overheats at') or [None])[0],
            'heat.heat_per_shot': (wiki_heat.get('Heat Per Shot') or [None])[0],
            'heat.heat_per_second': (wiki_heat.get('Heat Per Second') or [None])[0],
            'heat.cool_per_second': cooling[1] if len(cooling) >= 2 else None,
            'heatsink.starting': wiki_heat.get('startingMagazines'),
            'heatsink.from_supply': wiki_heat.get('magsFromSupply'),
            'heatsink.spare': wiki_heat.get('spareMagazines'),
        }
        direct = {
            'heat.capacity': (96, 'f32', _f32(body, 96)),
            'heat.heat_per_shot': (116, 'f32', _f32(body, 116)),
            'heat.heat_per_second': (120, 'f32', _f32(body, 120)),
            'heat.cool_per_second': (128, 'f32', _f32(body, 128)),
            'heatsink.starting': (84, 'u32', _u32(body, 84)),
            'heatsink.from_supply': (88, 'u32', _u32(body, 88)),
            'heatsink.spare': (92, 'u32', _u32(body, 92)),
        }
        unique = identity['resolution'] == 'UNIQUE' and owner['uniqueOwner']
        fields = []
        for field_id, (offset, storage, value) in direct.items():
            wiki_value = expected[field_id]
            matches = wiki_value is not None and math.isclose(value, wiki_value,
                rel_tol=1e-6, abs_tol=1e-5)
            fields.append({'id': field_id, 'value': value, 'wikiValue': wiki_value,
                'correlationMatches': matches, 'offset': offset, 'storage': storage,
                'owner': {'component': 'WeaponHeatComponentData',
                    'recordIndex': owner['recordIndex'], 'indexRow': owner['indexRow'],
                    'ownerCount': owner['ownerCount'], 'uniqueOwner': owner['uniqueOwner']},
                'writable': bool(unique and matches), 'writeScope': 'weapon_local',
                'reason': (None if unique and matches else
                    'Native value disagrees with the imported wiki value; semantic write remains fail-closed.'
                    if wiki_value is not None else
                    'The imported catalog has no matching semantic field for this native scalar.'
                    if unique else 'Ambiguous or shared WeaponHeat component ownership.')})
        fields.extend([
            {'id': 'heat.cool_per_second_cold', 'value': _f32(body, 128) * _f32(body, 136),
                'wikiValue': cooling[0] if len(cooling) >= 1 else None, 'derived': True,
                'writable': False, 'reason': 'Derived from cool_per_second and the native 1.5 cold multiplier.'},
            {'id': 'heat.cool_per_second_hot', 'value': _f32(body, 128) * _f32(body, 132),
                'wikiValue': cooling[2] if len(cooling) >= 3 else None, 'derived': True,
                'writable': False, 'reason': 'Derived from cool_per_second and the native 0.75 hot multiplier.'},
            {'id': 'heatsink.from_ammo_box', 'value': math.floor(_u32(body, 88) / 2),
                'wikiValue': wiki_heat.get('magsFromAmmoBox'), 'derived': True,
                'writable': False, 'reason': 'Derived from heatsink.from_supply.'},
            # 0.30.4 (research/las-beam-overhaul-comparison, heat148): the warm-up is the quotient of two members of
            # the weapon's own record, heat.firing_charge (+148) / heat.charge_gain_per_second (+152); no member of
            # its own. 0 when the weapon needs no charge.
            {'id': 'heat.warmup', 'value': warmup_seconds(_f32(body, 148), _f32(body, 152)),
                'wikiValue': (wiki_heat.get('Warmup') or [None])[0], 'derived': True,
                'writable': False, 'reason': WARMUP_REASON},
            # No dedicated overheat-lockout member: an overheated weapon cools from heat.capacity at
            # heat.cool_per_second (x the native cold / hot multipliers).
            {'id': 'heat.overheat_cooldown', 'value': None,
                'wikiValue': 'reload_needed' if 'Cooldown After Overheat' in wiki_heat else None,
                'derived': False, 'writable': False, 'reason': OVERHEAT_COOLDOWN_REASON},
        ])
        heat_weapons.append({'weapon': name, 'resources': identity['resources'],
            'heatMechanismPresent': True, 'heatsinkMechanismPresent': True,
            'componentIdentity': owner, 'wikiHeatData': wiki_heat, 'fields': fields,
            'reason': None})
    heat_groups = [{'recordIndex': record, 'weapons': sorted(consumers)}
        for record, consumers in sorted(heat_shared.items()) if len(consumers) > 1]
    heat = {**common, 'feature': 'player_weapon_heat_capabilities',
        'summary': {'weapons': 80,
            'weaponsWithHeatMechanism': sum(w['heatMechanismPresent'] for w in heat_weapons),
            'weaponsWithHeatsinkMechanism': sum(w['heatsinkMechanismPresent'] for w in heat_weapons),
            'directSemanticFieldsResolved': sum(1 for w in heat_weapons for f in w['fields']
                if not f.get('derived') and f.get('value') is not None),
            'writableFieldInstances': sum(f['writable'] for w in heat_weapons for f in w['fields']),
            'weaponsWithWritableHeatFields': sum(any(f['writable'] for f in w['fields']) for w in heat_weapons),
            'sharedComponentGroups': len(heat_groups),
            'heatsinkOptionIdentities': sum('heatsink' in option['name'].lower()
                for option in option_catalog),
            'writableHeatsinkOptionOverrides': 0},
        'layout': {'component': 'WeaponHeatComponentData', 'componentType': '0x4C981CD9',
            'recordSize': 592, 'capacityOffset': 96, 'heatPerShotOffset': 116,
            'heatPerSecondOffset': 120, 'coolPerSecondOffset': 128,
            'hotCoolingMultiplierOffset': 132, 'coldCoolingMultiplierOffset': 136,
            'startingHeatsinksOffset': 84, 'heatsinksFromSupplyOffset': 88,
            'spareHeatsinksOffset': 92},
        'findings': {'cooling': 'The native base at +128 exactly matches the middle wiki cooling rate for 7/7 weapons; +132=0.75 and +136=1.5 derive the hot/cold rates within wiki rounding.',
            'heatGeneration': 'Per-shot +116 matches 5/5 labelled projectile/shot weapons. Per-second +120 matches Scythe; Dagger uses a different native scale and remains read-only for generation.',
            'inventory': 'Starting +84 and spare +92 match 6/7; supply +88 matches 7/7. Dagger disagreements remain explicit and fail closed.',
            'capacity': 'Capacity +96 matches 6/7. Dagger stores 2000 while the catalog reports 100, so Dagger capacity remains read-only.',
            'attachmentOverrides': 'Nine native heatsink option identities are known, but no option-owned effect record or allowed-option graph is linked in this snapshot.'},
        'sharedGroups': heat_groups, 'weapons': heat_weapons}

    projectile_weapons = []
    writable_attacks = 0
    compatible_sources = defaultdict(list)
    terminal_weapons = []
    explosion_weapons = []
    explosion_types = {}
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
            shrapnel = any(_u32(bytes.fromhex(explosion['bytes']), 80) > 0
                for explosion in record['explosions'])
            compatibility = ('explosive_status' if explosive and status else
                'explosive_shrapnel' if shrapnel else
                'explosive_impact_and_expiry' if impact and expiry else
                'explosive_impact' if impact else 'explosive_expiry' if expiry else
                'status_bearing' if status else 'conventional_plain')
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
            approved_class = compatibility in {'conventional_plain', 'explosive_impact',
                'explosive_impact_and_expiry', 'explosive_shrapnel'}
            writable = unique_identity and target_owned and approved_class
            if writable:
                writable_attacks += 1
            item = {'role': role, 'projectileType': attack['projectileType'],
                'projectileSettings': attack['projectileSettings'], 'compatibilityClass': compatibility,
                'projectileObject': {'identity': attack['projectileSettings'],
                    'consumers': record['consumers'],
                    'scalarWriteScope': 'shared_projectile_definition',
                    'weaponLocalOverrideProven': False},
                'residency': package_residency_evidence.projectile_residency(name, role),
                'targetBacking': ({'component': component, 'offset': offset, 'width': 4,
                    'storage': 'u32', 'recordIndex': owner['recordIndex'],
                    'indexRow': owner['indexRow'], 'ownerCount': owner['ownerCount'],
                    'uniqueOwner': owner['uniqueOwner']} if owner else None),
                'sourceIdentityResolvable': unique_identity, 'targetOwnershipProven': target_owned,
                'writableReferenceSwap': writable,
                'reason': None if writable else ('ambiguous weapon identity' if not unique_identity else
                    'weapon-local projectile selector is absent or shared' if not target_owned else
                    'status or unsupported terminal companion graph is not approved for swapping')}
            attacks.append(item)
            if unique_identity and approved_class:
                compatible_sources[compatibility].append({'weapon': name, 'role': role,
                    'projectileType': attack['projectileType']})
            actions = []
            for phase, value, offset in (('impact', impact, 144), ('expiry', expiry, 156)):
                linked = next((x for x in record['references'] if x['offset'] == offset), None)
                if linked and linked['explosionRecord']:
                    explosion_offset_hits[offset] += 1
                distinct_consumers = sorted({consumer['resourceHash'] for consumer in record['consumers']})
                # Zero is the native no-action sentinel. It occurs in the same two typed
                # slots as non-zero ExplosionSettings references, so it can be guarded as
                # a typed null without accepting an arbitrary integer.
                writable_action = bool(unique_identity and (value == 0 or
                    (linked and linked['explosionRecord'])))
                actions.append({'phase': phase, 'offset': offset, 'width': 4, 'storage': 'u32',
                    'referenceType': value, 'actionKind': 'explosion' if value else 'none',
                    'linkedExplosionRecord': bool(linked and linked['explosionRecord']),
                    'readable': True, 'writable': writable_action,
                    'referenceClass': 'ExplosionSettings?', 'nullSentinel': 0,
                    'projectileSettingsConsumers': record['consumers'],
                    'affectsMultipleResources': len(distinct_consumers) > 1,
                    'reason': (None if writable_action else
                        'Ambiguous weapon identity blocks an ordinary typed terminal write.')})
            for ref in record['references']:
                if ref['value']:
                    neighbor_nonzero[ref['offset']] += 1
            terminal_attacks.append({'role': role, 'projectileType': attack['projectileType'],
                'projectileSettings': attack['projectileSettings'], 'actions': actions})
            explosion_entries = []
            for explosion in record['explosions']:
                explosion_bytes = bytes.fromhex(explosion['bytes'])
                damage_bytes = bytes.fromhex(explosion['damage']['bytes'])
                distinct_projectiles = sorted({consumer['projectileType'] for consumer in explosion['consumers']})
                damage_consumers = sorted(set(explosion['damage']['consumers']))
                shared = len(distinct_projectiles) > 1 or len(damage_consumers) > 1
                player_consumers = []
                for consumer_weapon in raw['weapons']:
                    for consumer_attack in consumer_weapon['projectiles']:
                        if consumer_attack['projectileType'] in distinct_projectiles:
                            player_consumers.append({'weapon': consumer_weapon['name'],
                                'role': consumer_attack['role'],
                                'projectileType': consumer_attack['projectileType']})
                fields = [
                    {'id': 'explosion.inner_radius', 'offset': 16, 'storage': 'f32',
                        'type': 'number', 'unit': 'meters', 'value': _f32(explosion_bytes, 16)},
                    {'id': 'explosion.outer_radius', 'offset': 20, 'storage': 'f32',
                        'type': 'number', 'unit': 'meters', 'value': _f32(explosion_bytes, 20)},
                    {'id': 'explosion.shockwave_radius', 'offset': 24, 'storage': 'f32',
                        'type': 'number', 'unit': 'meters', 'value': _f32(explosion_bytes, 24)},
                ]
                for field_id, offset, storage in (
                    ('explosion.damage.standard_damage', 4, 'i32'),
                    ('explosion.damage.durable_damage', 8, 'i32'),
                    ('explosion.damage.ap_direct', 12, 'u32'),
                    ('explosion.damage.ap_slight', 16, 'u32'),
                    ('explosion.damage.ap_large', 20, 'u32'),
                    ('explosion.damage.ap_extreme', 24, 'u32'),
                    ('explosion.damage.demolition', 28, 'u32'),
                    ('explosion.damage.stagger', 32, 'u32'),
                    ('explosion.damage.push_force', 36, 'u32')):
                    fields.append({'id': field_id, 'offset': offset, 'storage': storage,
                        'type': 'integer', 'unit': 'damage' if offset in (4, 8) else
                            'armor_class' if offset in (12, 16, 20, 24) else 'force',
                        'value': _i32(damage_bytes, offset) if storage == 'i32' else _u32(damage_bytes, offset)})
                shrapnel_count = _u32(explosion_bytes, 80)
                shrapnel_type = _u32(explosion_bytes, 84)
                shrapnel_record = next((reference for reference in explosion['projectileReferences']
                    if reference['offset'] == 84 and reference['projectileType'] == shrapnel_type), None)
                entry = {'explosionType': explosion['explosionType'],
                    'settings': explosion['settings'], 'damageType': explosion['damageType'],
                    'damageSettings': {key: explosion['damage'][key] for key in
                        ('group', 'row', 'recordType', 'settingsType')},
                    'fields': fields, 'consumers': explosion['consumers'],
                    'playerConsumers': sorted(player_consumers, key=lambda value: (value['weapon'], value['role'])),
                    'damageConsumers': damage_consumers, 'shared': shared,
                    'writeScope': 'shared_settings' if shared else 'projectile_terminal_actions',
                    'writable': unique_identity, 'writableScalarFields': len(fields) if unique_identity else 0,
                    'reason': None if unique_identity else 'Ambiguous weapon resource identity blocks ordinary writes.',
                    'shrapnel': {'count': shrapnel_count, 'projectileType': shrapnel_type or None,
                        'projectileSettings': shrapnel_record['settings'] if shrapnel_record else None,
                        'structurallyProven': bool(shrapnel_count and shrapnel_record),
                        'writableCount': False, 'writableProjectileReference': False,
                        'reason': 'One correlated schema instance is insufficient to promote shrapnel writes.'}}
                explosion_entries.append(entry)
                explosion_types.setdefault(explosion['explosionType'], entry)
            if explosion_entries:
                explosion_weapons.append({'weapon': name, 'role': role,
                    'projectileType': attack['projectileType'], 'explosions': explosion_entries})
        projectile_weapons.append({'weapon': name, 'resources': identity['resources'],
            'resolution': identity['resolution'], 'implementationFamilies': candidate['implementationFamilies'],
            'attacks': attacks})
        terminal_weapons.append({'weapon': name, 'resources': identity['resources'],
            'resolution': identity['resolution'], 'attacks': terminal_attacks})
    projectile_groups = defaultdict(list)
    for weapon in projectile_weapons:
        for attack in weapon['attacks']:
            settings=attack['projectileSettings']
            projectile_groups[(settings['group'],settings['row'],settings['recordType'])].append(
                {'weapon':weapon['weapon'],'role':attack['role'],
                    'projectileType':attack['projectileType']})
    shared_projectile_groups=[{'settings': {'group':key[0],'row':key[1],'recordType':key[2]},
        'consumers':sorted(value,key=lambda item:(item['weapon'],item['role']))}
        for key,value in sorted(projectile_groups.items()) if len(value)>1]
    projectile = {**common, 'feature': 'projectile_reference_graph',
        'summary': {'weapons': 80, 'weaponsWithProjectileAttack': sum(bool(w['attacks']) for w in projectile_weapons),
            'projectileAttacks': sum(len(w['attacks']) for w in projectile_weapons),
            'writableTargetAttacks': writable_attacks,
            'compatibleSourceAttacks': sum(map(len, compatible_sources.values())),
            'writableExplosiveSelectors': sum(1 for weapon in projectile_weapons for attack in weapon['attacks']
                if attack['writableReferenceSwap'] and attack['compatibilityClass'].startswith('explosive_')),
            'sharedProjectileGroups': len(shared_projectile_groups),
            'compatibilityClasses': {key: len(value) for key, value in sorted(compatible_sources.items())}},
        'guardPolicy': {'operationKind': 'typed_reference_replacement',
            'allowed': 'same reviewed structural class only',
            'approvedClasses': sorted(compatible_sources),
            'sourceSettingsMutated': False, 'expectedReferenceRequired': True,
            'sourceIdentityMustResolveUniquely': True,
            'sharedTargetPolicy': 'fail_closed; no shared target selector is promoted in this pass'},
        'compatibleSourcesByClass': dict(sorted(compatible_sources.items())),
        'sharedProjectileGroups': shared_projectile_groups,
        'residencyPolicy': apply_projectile_residency.residency_policy(projectile_weapons),
        'weapons': projectile_weapons}

    fire_groups = defaultdict(list)
    fire_vectors = defaultdict(list)
    fire_weapons = []
    for name in sorted(author_by_name):
        identity = author_by_name[name]; candidate = candidate_by_name[name]
        value = candidate['resolvedFields'].get('primary_fire_mode')
        if value is not None:
            fire_groups[str(value)].append(name)
        owner = candidate['ownership'].get('WeaponDataComponentData')
        component = raw_by_name[name]['components'].get('WeaponDataComponentData')
        component_bytes = bytes.fromhex(component['bytes']) if component else b''
        vector = [_u32(component_bytes, offset) for offset in (144, 148, 152)] \
            if len(component_bytes) >= 156 else []
        fire_vectors[str(tuple(vector))].append(name)
        conventional = 'conventional_projectile' in candidate['implementationFamilies']
        allowed = [mode for mode in vector if mode]
        semantics = ({1: 'full_auto', 2: 'semi_auto'}.get(value)
            if conventional else None)
        safe_modes = [mode for mode in allowed if mode in (1, 2)] if conventional else []
        unique = identity['resolution'] == 'UNIQUE'
        writable = unique and len(set(safe_modes)) > 1
        fire_weapons.append({'weapon': name, 'resources': identity['resources'],
            'implementationFamilies': candidate['implementationFamilies'],
            'primaryFireModeNativeValue': value,
            'backing': ({'component': 'WeaponDataComponentData', 'offset': 144, 'width': 4,
                'storage': 'u32', 'recordIndex': owner['recordIndex'], 'indexRow': owner['indexRow']}
                if owner and value is not None else None),
            'nativeModeVector': vector, 'allowedModes': safe_modes,
            'defaultModeSemantics': semantics or 'family_specific_or_unresolved',
            'selectedRuntimeMode': None, 'writable': writable,
            'writeKind': 'reorder_native_mode_vector' if writable else None,
            'reason': (None if writable else
                'Only conventional, uniquely resolved weapons with both native 1 and 2 in their three-slot vector are writable.')})
    fire_mode = {**common, 'feature': 'fire_mode_graph',
        'summary': {'weapons': 80, 'nativePrimaryValueReadable': sum(w['primaryFireModeNativeValue'] is not None for w in fire_weapons),
            'allowedModeListsProven': sum(bool(w['nativeModeVector']) for w in fire_weapons),
            'writableWeapons': sum(w['writable'] for w in fire_weapons)},
        'nativeValueGroups': dict(sorted(fire_groups.items())),
        'nativeModeVectors': dict(sorted(fire_vectors.items())),
        'findings': {'primaryValue': {'component': 'WeaponDataComponentData', 'offset': 144,
            'storage': 'u32', 'vectorOffsets': [144, 148, 152]},
            'nativeValues': {'1': 'Full Auto for conventional projectile consumers; family-specific held trigger elsewhere.',
                '2': 'Semi Auto for conventional projectile consumers; family-specific trigger elsewhere.',
                '3': 'Special sequence/guided/burst-like; not sufficiently uniform to name as Burst.',
                '5': 'Charge-controlled on PLAS-15 Loyalist; not promoted as a general enum.'},
            'rateSelector': 'Separate from fire-mode selection; no player-weapon rate selector graph was proven.',
            'jar5FullAuto': 'Blocked: JAR-5 vector is [2,3,0]; native Full Auto value 1 is not an allowed member.'},
        'weapons': fire_weapons}

    terminal = {**common, 'feature': 'projectile_terminal_action_graph',
        'summary': {'weapons': 80, 'projectileAttacks': sum(len(w['attacks']) for w in terminal_weapons),
            'readableActions': sum(2 * len(w['attacks']) for w in terminal_weapons),
            'writableActions': sum(action['writable'] for weapon in terminal_weapons
                for attack in weapon['attacks'] for action in attack['actions']),
            'writableImpactRefs': sum(action['writable'] and action['phase'] == 'impact'
                for weapon in terminal_weapons for attack in weapon['attacks'] for action in attack['actions']),
            'writableExpiryRefs': sum(action['writable'] and action['phase'] == 'expiry'
                for weapon in terminal_weapons for attack in weapon['attacks'] for action in attack['actions']),
            'impactExplosionLinks': explosion_offset_hits[144],
            'expiryExplosionLinks': explosion_offset_hits[156]},
        'layout': {'record': 'ProjectileSettings', 'recordSize': 272,
            'impact': {'offset': 144, 'schemaLabel': 'ProjectileInfo.ExplosionType'},
            'expiry': {'offset': 156, 'schemaLabel': 'lifetime-end explosion candidate'}},
        'neighborReferenceEvidence': [{'offset': offset, 'nonzeroRecords': neighbor_nonzero[offset],
            'linkedExplosionRecords': explosion_offset_hits[offset]} for offset in range(128, 177, 4)],
        'findings': {'impact': 'Schema-labelled ExplosionType and structurally linked ExplosionSettings records; typed replacement is guarded.',
            'expiry': 'All nonzero current records link the same typed ExplosionSettings table and share the impact reference contract.',
            'null': 'Zero is the repeatedly observed native no-action sentinel in both typed slots; raw numeric zero remains rejected.',
            'otherActions': 'Neighboring nonzero scalars are not promoted without typed ownership or consumer evidence.'},
        'weapons': terminal_weapons}
    explosion = {**common, 'feature': 'explosion_authoring_capabilities',
        'summary': {'weaponsWithExplosions': len({item['weapon'] for item in explosion_weapons}),
            'explosiveProjectileAttacksResolved': len(explosion_weapons),
            'explosionSettingsResolved': len(explosion_types),
            'explosionScalarFieldsWritable': sum(item['writableScalarFields'] for item in explosion_types.values()),
            'sharedExplosionGroups': sum(item['shared'] for item in explosion_types.values()),
            'shrapnelGraphsResolved': sum(item['shrapnel']['structurallyProven'] for item in explosion_types.values()),
            'shrapnelWrites': 0},
        'layout': {'ExplosionSettings': {'recordSize': 152, 'damageTypeOffset': 4,
            'innerRadiusOffset': 16, 'outerRadiusOffset': 20, 'shockwaveRadiusOffset': 24,
            'shrapnelCountOffset': 80, 'shrapnelProjectileOffset': 84},
            'DamageInfo': {'recordSize': 76}},
        'guardPolicy': {'sharedSettingsRequireAllowShared': True,
            'typedReferencesOnly': True, 'rawExplosionIdsRejected': True,
            'outerDamage': 'No independent outer-damage scalar was proven; radial falloff remains read-only native behavior.'},
        'explosions': [explosion_types[key] for key in sorted(explosion_types)],
        'weapons': explosion_weapons}
    return {'magazine': magazine, 'projectile': projectile, 'fire_mode': fire_mode,
        'terminal': terminal, 'explosion': explosion, 'heat': heat}


def write(reports):
    for key, path in OUTPUTS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports[key], indent=2) + '\n')
    # Compatibility filenames remain available to existing SDK consumers.
    (ROOT / 'sdk/PlayerWeaponMagazineOptionGraph.json').write_text(
        json.dumps(reports['magazine'], indent=2) + '\n')
    (ROOT / 'sdk/PlayerWeaponProjectileReferenceGraph.json').write_text(
        json.dumps(reports['projectile'], indent=2) + '\n')
    HEAT_RESEARCH.write_text(json.dumps(reports['heat'], indent=2) + '\n')
    ATTACHMENTS_CATALOG.write_text(json.dumps({'schemaVersion': 1,
        'importer': reports['magazine']['importer'], 'summary': reports['magazine']['summary'],
        'weapons': reports['magazine']['weapons']}, indent=2) + '\n')
    magazines = {item['weapon']: item for item in reports['magazine']['weapons']}
    projectiles = {item['weapon']: item for item in reports['projectile']['weapons']}
    fire_modes = {item['weapon']: item for item in reports['fire_mode']['weapons']}
    terminals = {item['weapon']: item for item in reports['terminal']['weapons']}
    explosions = defaultdict(dict)
    for item in reports['explosion']['weapons']:
        explosions[item['weapon']][item['role']] = item['explosions']
    heat = {item['weapon']: item for item in reports['heat']['weapons']}
    catalog = {'schemaVersion': 1, 'sourceSnapshot': SNAPSHOT.name,
        'hd2RuntimeVersion': reports['projectile']['hd2RuntimeVersion'],
        'gameFingerprints': reports['projectile']['gameFingerprints'],
        'summary': {key: value['summary'] for key, value in reports.items()}, 'weapons': {}}
    for name in sorted(magazines):
        terminal_by_role = {item['role']: item['actions'] for item in terminals[name]['attacks']}
        catalog['weapons'][name] = {
            'magazine': {'simpleApi': magazines[name]['simpleMagazineApi'],
                'defaultOption': magazines[name]['defaultOption'],
                'observedOptions': magazines[name]['observedCustomizationOptions'],
                'attachmentCategories': magazines[name]['categories']},
            'fireMode': {'nativeValue': fire_modes[name]['primaryFireModeNativeValue'],
                'nativeModeVector': fire_modes[name]['nativeModeVector'],
                'allowedModes': fire_modes[name]['allowedModes'],
                'defaultModeSemantics': fire_modes[name]['defaultModeSemantics'],
                'backing': fire_modes[name]['backing'],
                'writable': fire_modes[name]['writable'],
                'writeKind': fire_modes[name]['writeKind'],
                'reason': fire_modes[name]['reason']},
            'heat': heat[name],
            'attacks': [{**attack,
                'aliases': (['primary'] if index == 0 else ['alternate']),
                'terminalActions': terminal_by_role.get(attack['role'], []),
                'explosions': explosions[name].get(attack['role'], [])}
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
