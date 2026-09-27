"""Targeted, read-only attachment preset extraction and state comparison.

The extractor resolves only the reviewed 80 player-weapon roots and the five
components relevant to attachment selection/effects.  It does not scan payload
bytes for arbitrary values and never constructs a writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'build/weapon-composition-raw.json'
ATTACHMENTS = ROOT / 'sdk/AttachmentOptionCapabilities.json'
OUTPUTS = {
    'preset': ROOT / 'sdk/AttachmentPresetGraph.json',
    'selection': ROOT / 'sdk/AttachmentSelectionCapabilities.json',
    'effects': ROOT / 'sdk/AttachmentEffectOwnership.json',
    'diff': ROOT / 'research/attachment-targeted-diff-F5FEE03DCFDB.json',
}
COMPONENTS = ('WeaponCustomizationComponentData', 'WeaponMagazineComponentData',
    'WeaponRoundsComponentData', 'WeaponDataComponentData', 'WeaponHeatComponentData')

sys.path.insert(0, str(ROOT / 'sdk'))
from tools.lua_runner import execute


def _lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + _lua(k) + ']=' + _lua(v) for k, v in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '{' + ','.join(_lua(item) for item in value) + '}'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def _module_sources():
    result = {}
    for folder in ('api', 'core', 'runtime', 'schemas', 'domains', 'primary_mapper'):
        for path in sorted((ROOT / folder).glob('*.lua')):
            result['hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()] = path.read_text()
    return result


def scan_snapshot(snapshot, label):
    """Extract only reviewed attachment-related components from one snapshot."""
    authoring = json.loads((ROOT / 'schemas/player_weapon_authoring_catalog.json').read_text())
    requested = [{'name': item['name'], 'resource': item['resources'][0]}
        for item in authoring['weapons']]
    preload = '\n'.join('package.preload[' + _lua(name)
        + ']=function(...) return assert(loadstring(' + _lua(body) + ',' + _lua(name)
        + '))(...) end' for name, body in _module_sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(Path(snapshot).resolve())) + r''',{
  expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
 local reader=Reader.new(source)
 local roots=discover.locate(source,reader,profile,{entity=true})
 local names=''' + _lua(COMPONENTS) + r'''
 local catalog=entities.capture(reader,roots.entity,profile,names)
 local by_resource={};for _,candidate in ipairs(catalog.candidates)do
  by_resource[candidate.resourceHash]=candidate end
 local result={mode='snapshot',fingerprints={exe=source.module_hash(source.module(nil)),
  dll=source.module_hash(source.module('game.dll'))},weapons={},writes=0,
  protectionChanges=0,fixtureFallback='disabled'}
 for _,item in ipairs(''' + _lua(requested) + r''')do
  local candidate=assert(by_resource[item.resource],'reviewed attachment root missing: '..item.resource)
  assert(candidate.entityRow and#candidate.diagnostics==0,'attachment root ownership unresolved: '..item.resource)
  local output={name=item.name,resourceHash=item.resource,components={}}
  for _,name in ipairs(names)do if candidate.ownership[name]then
   local record=catalog.record(candidate,name)
   output.components[name]={identity=record.identity,bytes=(record.bytes:gsub('.',function(c)
    return string.format('%02x',c:byte())end)),length=#record.bytes}
  end end
  result.weapons[#result.weapons+1]=output
 end
 reader.stage='attachment_preset_research:stable_reread';reader.verify();source.close()
 return result
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''
    raw = json.loads(execute(program.encode()))
    raw['sourceSnapshot'] = Path(snapshot).name
    return state_from_composition_raw(raw, label)


def _defaults(body: bytes):
    result = []
    for offset in range(0, 80, 8):
        slot, option = struct.unpack_from('<II', body, offset)
        if slot == 0:
            break
        result.append({'slot': slot, 'optionId': f'0x{option:08X}', 'offset': offset})
    return result


def _component_state(component):
    body = bytes.fromhex(component['bytes'])
    result = {'identity': component['identity'], 'length': len(body),
        'sha256': hashlib.sha256(body).hexdigest(), 'bytes': component['bytes']}
    if component['identity']['component'] == 'WeaponCustomizationComponentData':
        result['defaultDefinitions'] = _defaults(body)
    return result


def state_from_composition_raw(raw, label):
    source_snapshot = raw.get('sourceSnapshot')
    if not source_snapshot and ATTACHMENTS.is_file():
        source_snapshot = json.loads(ATTACHMENTS.read_text()).get('sourceSnapshot')
    weapons = []
    for weapon in raw['weapons']:
        components = {name: _component_state(value) for name, value in weapon['components'].items()
            if name in COMPONENTS}
        weapons.append({'weapon': weapon['name'], 'resourceHash': weapon['resourceHash'],
            'components': components})
    return {'schemaVersion': 1, 'label': label, 'mode': raw.get('mode', 'snapshot'),
        'sourceSnapshot': source_snapshot, 'gameFingerprints': raw['fingerprints'],
        'safety': {'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'},
        'weapons': weapons}


def _ranges(before: bytes, after: bytes):
    assert len(before) == len(after)
    ranges = []
    start = None
    for offset, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = offset
        if left == right and start is not None:
            ranges.append((start, offset)); start = None
    if start is not None:
        ranges.append((start, len(before)))
    return ranges


def _word_views(before, after, first, last):
    views = []
    for offset in range(first - first % 4, min(len(before), last + 3), 4):
        if before[offset:offset + 4] == after[offset:offset + 4] or offset + 4 > len(before):
            continue
        left = struct.unpack_from('<I', before, offset)[0]
        right = struct.unpack_from('<I', after, offset)[0]
        left_f = struct.unpack_from('<f', before, offset)[0]
        right_f = struct.unpack_from('<f', after, offset)[0]
        views.append({'offset': offset, 'beforeU32': left, 'afterU32': right,
            'beforeF32': left_f if math.isfinite(left_f) else None,
            'afterF32': right_f if math.isfinite(right_f) else None})
    return views


def compare_states(before, after):
    if before['gameFingerprints'] != after['gameFingerprints']:
        raise ValueError('attachment states use different game fingerprints')
    prior = {(item['weapon'], item['resourceHash']): item for item in before['weapons']}
    current = {(item['weapon'], item['resourceHash']): item for item in after['weapons']}
    if prior.keys() != current.keys():
        raise ValueError('attachment state weapon roots differ')
    changes = []
    for key in sorted(prior):
        left, right = prior[key], current[key]
        names = set(left['components']) | set(right['components'])
        for name in sorted(names):
            if name not in left['components'] or name not in right['components']:
                changes.append({'weapon': key[0], 'resourceHash': key[1], 'component': name,
                    'kind': 'ownership_changed'})
                continue
            a = bytes.fromhex(left['components'][name]['bytes'])
            b = bytes.fromhex(right['components'][name]['bytes'])
            if a == b:
                continue
            if len(a) != len(b):
                changes.append({'weapon': key[0], 'resourceHash': key[1], 'component': name,
                    'kind': 'record_extent_changed', 'beforeLength': len(a), 'afterLength': len(b)})
                continue
            ranges = []
            for first, last in _ranges(a, b):
                ranges.append({'offset': first, 'length': last - first,
                    'before': a[first:last].hex(), 'after': b[first:last].hex(),
                    'alignedScalarViews': _word_views(a, b, first, last)})
            entry = {'weapon': key[0], 'resourceHash': key[1], 'component': name,
                'kind': 'bytes_changed', 'ranges': ranges}
            if name == 'WeaponCustomizationComponentData':
                entry['beforeDefaultDefinitions'] = _defaults(a)
                entry['afterDefaultDefinitions'] = _defaults(b)
            changes.append(entry)
    return {'before': before['label'], 'after': after['label'], 'changedRecords': len(changes),
        'changes': changes}


def _flatten_options(capabilities):
    for weapon in capabilities['weapons']:
        for category in weapon['categories']:
            for option in category['options']:
                yield weapon, category['category'], option


def build_reports(states):
    capabilities = json.loads(ATTACHMENTS.read_text())
    version = (ROOT / 'VERSION').read_text().strip()
    safety = {'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled',
        'snapshotOnly': True}
    comparisons = [compare_states(states[index - 1], states[index])
        for index in range(1, len(states))]
    all_options = list(_flatten_options(capabilities))
    native_options = sum(option.get('optionIdentityProven', False)
        for _, _, option in all_options)
    native_catalog = capabilities.get('nativeMagazineOptions', [])
    heatsink_identities = sum('heatsink' in item['name'].lower() for item in native_catalog)
    native_defaults = sum(weapon.get('defaultOption') is not None
        and weapon['defaultOption'].get('optionIdentityProven', False)
        for weapon in capabilities['weapons'])
    common = {'schemaVersion': 1, 'hd2RuntimeVersion': version,
        'gameFingerprints': capabilities['gameFingerprints'], 'safety': safety,
        'evidenceStates': [{'label': state['label'], 'mode': state['mode'],
            'sourceSnapshot': state.get('sourceSnapshot')} for state in states]}

    preset_weapons = []
    selection_rows = []
    effect_rows = []
    effect_fields = {}
    for weapon in capabilities['weapons']:
        categories = []
        for category in weapon['categories']:
            options = []
            for option in category['options']:
                native = option.get('nativeOption')
                default_definition = bool(option.get('default') and native)
                reason = ('The generated component definition proves this default identity, '
                    'but no current/saved preset selection owner or alternate allowed-option '
                    'collection is present in the available state capture.' if default_definition else
                    'Catalog compatibility is known; native option identity and current/saved '
                    'selection ownership are not proven.')
                row = {'weapon': weapon['weapon'], 'resources': weapon['resources'],
                    'category': category['category'], 'option': option['name'],
                    'typedHandleAvailable': True, 'catalogAllowed': True,
                    'nativeOption': native, 'defaultDefinition': default_definition,
                    'currentSelectionReadable': False, 'savedPresetReadable': False,
                    'selectionOwner': None, 'writable': False, 'reason': reason}
                selection_rows.append(row)
                effects = option.get('effects') or {}
                candidates = []
                for field, value in sorted(effects.items()):
                    if value in ([], None):
                        continue
                    effect_fields[field] = effect_fields.get(field, 0) + 1
                    candidates.append({'field': field, 'catalogValue': value,
                        'nativeOwner': None, 'scope': 'unknown', 'writable': False})
                effect_rows.append({'weapon': weapon['weapon'], 'category': category['category'],
                    'option': option['name'], 'nativeOption': native, 'effects': candidates,
                    'applicationOwner': None, 'copiedEffectiveState': 'unproven',
                    'sharedConsumers': None, 'writable': False,
                    'reason': 'Normalized effects are correlation fingerprints; no option-owned or preset-local application record is linked.'})
                options.append({'name': option['name'], 'defaultDefinition': default_definition,
                    'nativeOption': native, 'effectFieldCount': len(candidates),
                    'selectionWritable': False, 'effectsWritable': False})
            categories.append({'category': category['category'], 'options': options})
        preset_weapons.append({'weapon': weapon['weapon'], 'resources': weapon['resources'],
            'componentDefault': weapon.get('defaultOption'), 'categories': categories})

    preset = {**common, 'feature': 'attachment_preset_graph',
        'summary': {'weapons': 80, 'attachmentOptions': len(all_options),
            'knownNativeOptionCatalogIdentities': len(native_catalog),
            'nativeOptionIdentitiesTiedToRows': native_options,
            'nativeDefaultRelationships': native_defaults,
            'stateCapturesCompared': len(comparisons), 'selectedAttachmentOwnersProven': 0,
            'savedPresetOwnersProven': 0, 'writablePresetFields': 0},
        'nativeLayout': {'component': 'WeaponCustomizationComponentData', 'recordSize': 4872,
            'defaultDefinitions': {'offset': 0, 'entryStride': 8, 'entryCount': 10,
                'slotOffset': 0, 'optionIdOffset': 4, 'terminatorSlot': 0,
                'meaning': 'Generated weapon-resource default definition; not proven current player selection.'},
            'selectedAttachmentState': None, 'savedPresetState': None,
            'effectApplicationRecord': None},
        'ownershipFindings': {
            'weaponPresetStateFound': False,
            'defaultDefinitionOwner': 'weapon resource WeaponCustomizationComponentData',
            'selectedAttachmentOwner': None, 'savedPresetOwner': None,
            'spawnRebuildBehavior': 'unresolved; requires selected/saved/re-equipped state captures',
            'importantDistinction': 'DefaultCustomizations is static resource data and is not promoted as current selection or saved preset state.'},
        'nativeIdentityCatalog': native_catalog, 'weapons': preset_weapons}
    selection = {**common, 'feature': 'attachment_selection_capabilities',
        'summary': {'attachmentOptions': len(selection_rows),
            'knownNativeOptionCatalogIdentities': len(native_catalog),
            'nativeIdentitiesTiedToRows': native_options,
            'magazineOptions': sum(row['category'] == 'Magazine' for row in selection_rows),
            'writableSelections': 0, 'writableMagazineSelections': 0,
            'knownNativeHeatsinkIdentities': heatsink_identities,
            'writableHeatsinkSelections': 0},
        'guardPolicy': {'typedHandlesOnly': True, 'rawOptionIdsRejected': True,
            'rawAddPathsRejected': True, 'compatibilityMustBeNative': True,
            'currentSelectionMustBeVerified': True, 'status': 'read_only'},
        'unboundNativeIdentityCatalog': native_catalog, 'options': selection_rows}
    effects = {**common, 'feature': 'attachment_effect_ownership',
        'summary': {'attachmentOptions': len(effect_rows),
            'normalizedEffectInstances': sum(len(row['effects']) for row in effect_rows),
            'effectFieldKinds': len(effect_fields), 'optionEffectOwnersProven': 0,
            'writableEffectFields': 0, 'sharedGlobalDefinitionsProven': 0,
            'heatsinkEffectOwnersProven': 0},
        'effectFieldOccurrences': dict(sorted(effect_fields.items())),
        'ownershipFindings': {'optionDefinitionOwner': None, 'presetLocalOverrideOwner': None,
            'copiedEffectiveStateOwner': None, 'sharedness': 'unresolved',
            'heatApplicationPath': 'Direct WeaponHeat values remain proven, but no heatsink option-to-effective-value consumer edge is captured.'},
        'options': effect_rows}
    baseline_fingerprints = []
    anchors = {'AR-23 Liberator', 'AR-23C Liberator Concussive', 'LAS-5 Scythe',
        'LAS-16 Sickle', 'LAS-17 Double-Edge Sickle', 'LAS-7 Dagger'}
    for state in states:
        records = []
        for weapon in state['weapons']:
            if weapon['weapon'] not in anchors:
                continue
            records.append({'weapon': weapon['weapon'], 'resourceHash': weapon['resourceHash'],
                'components': {name: {'recordIndex': value['identity']['recordIndex'],
                    'length': value['length'], 'sha256': value['sha256'],
                    'defaultDefinitions': value.get('defaultDefinitions')}
                    for name, value in weapon['components'].items()}})
        baseline_fingerprints.append({'label': state['label'], 'records': records})
    diff = {**common, 'feature': 'attachment_targeted_state_diff',
        'summary': {'states': len(states), 'comparisons': len(comparisons),
            'changedRecords': sum(item['changedRecords'] for item in comparisons),
            'result': 'COMPARED' if comparisons else 'INSUFFICIENT_STATE_CAPTURES'},
        'scope': {'weapons': 80, 'components': list(COMPONENTS),
            'broadNumericScan': False, 'arbitraryAddressScan': False},
        'stateFingerprints': baseline_fingerprints, 'comparisons': comparisons,
        'requiredExperiment': [
            {'label': 'ar23c_extended_equipped', 'action': 'Equip AR-23C with Extended magazine; capture before editing.'},
            {'label': 'ar23c_short_selected', 'action': 'Select Short magazine without saving; capture.'},
            {'label': 'ar23c_short_saved', 'action': 'Save the preset; capture.'},
            {'label': 'ar23c_short_reequipped', 'action': 'Re-equip/spawn the saved preset; capture.'},
            {'label': 'ar23c_drum_selected', 'action': 'Select Drum magazine; capture.'},
            {'label': 'optic_selected', 'action': 'Change one optic on the same weapon; capture.'},
            {'label': 'heatsink_selected', 'action': 'Change one Sickle/Scythe heatsink option; capture.'}],
        'promotionGate': 'No selection/effect field is writable until repeated deltas prove identity, semantics, ownership, scope, and consumer behavior.'}
    return {'preset': preset, 'selection': selection, 'effects': effects, 'diff': diff}


def write_reports(reports):
    for name, path in OUTPUTS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports[name], indent=2) + '\n')


def _named(value):
    if '=' not in value:
        raise argparse.ArgumentTypeError('state must be LABEL=PATH')
    label, path = value.split('=', 1)
    return label, Path(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-state', action='append', type=_named,
        help='LABEL=weapon-composition-raw.json; repeat in capture order')
    parser.add_argument('--snapshot-state', action='append', type=_named,
        help='LABEL=snapshot.hd2snap; repeat in capture order')
    parser.add_argument('--state-output-dir', type=Path,
        help='Optional directory for compact extracted state JSON files')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.raw_state and args.snapshot_state:
        parser.error('use either --raw-state or --snapshot-state')
    if args.snapshot_state:
        states = [scan_snapshot(path, label) for label, path in args.snapshot_state]
    else:
        inputs = args.raw_state or [('current_snapshot_unknown_preset', RAW)]
        states = [state_from_composition_raw(json.loads(path.read_text()), label)
            for label, path in inputs]
    if args.state_output_dir:
        args.state_output_dir.mkdir(parents=True, exist_ok=True)
        for state in states:
            (args.state_output_dir / (state['label'] + '.attachment-state.json')).write_text(
                json.dumps(state, indent=2) + '\n')
    reports = build_reports(states)
    if args.check:
        for name, path in OUTPUTS.items():
            if json.loads(path.read_text()) != reports[name]:
                raise SystemExit(f'generated attachment research is stale: {path}')
    else:
        write_reports(reports)
    print(json.dumps({name: report['summary'] for name, report in reports.items()}, indent=2))


if __name__ == '__main__':
    main()
