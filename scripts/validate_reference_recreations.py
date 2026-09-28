"""Prove the recreation example projects reproduce the reference mods' native edits 1:1.

Each example addon is executed with a validating adapter, then every plan phase is
resolved by the production write domains against the retained snapshot and
prepared exactly as hd2.plan would prepare it. Nothing is written. The resulting
physical write set (component record, record-relative field offset, original and
replacement bytes) must equal the write set pinned by each reference mod's own
source constants.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
OUTPUT = ROOT / 'validation/reference-mod-recreations.json'


def f32(value): return struct.pack('<f', value).hex()
def i32(value): return struct.pack('<i', value).hex()
def u32(value): return struct.pack('<I', value).hex()
def u64(value): return struct.pack('<Q', value).hex()


def bastion_writes(record):
    # BastionReArmored armored_16000: src/release/validate.lua + src/armor_proof/validate.lua.
    writes = {('HealthComponentData', record, 0, i32(8000), i32(16000)),
        ('HealthComponentData', record, 64 + 216, u32(4), u32(5))}
    for zone in list(range(0, 6)) + list(range(12, 31)):
        writes.add(('HealthComponentData', record, 520 + zone * 552 + 216, u32(4), u32(5)))
    for zone in (3, 4):  # src/lunchbox_proof/validate.lua: +0x978 / +0xBA0
        writes.add(('HealthComponentData', record, 520 + zone * 552 + 248, f32(1.0), f32(0.0)))
    return writes


def concussive_drum_writes():
    # Derived from the retained native research: the drum attachment's own delta record.
    research = json.loads((ROOT / 'research/magazine-attachments-F5FEE03DCFDB.json').read_text())
    drum = next(item for item in research['magazineAttachments'] if item['debugName'] == 'Rifle 5,5x50mm. Drum')
    return {('EntityDelta:WeaponMagazineComponentData', drum['settingsIndex'], 136, u32(60), u32(90))}


# Record indices and offsets are copied from each mod's source (see REFERENCES).
EXPECTED = {
    'ShieldRelayRecreation': {
        ('StratagemDefinition', None, 104, f32(90), f32(180)),
        ('ShieldComponentData', 12, 0, f32(15), f32(8)),
        ('ShieldComponentData', 12, 76, f32(4000), f32(40000)),
        ('HellpodPayloadComponentData', 3, 4, f32(40), f32(90)),
        ('HealthComponentData', 309, 0, i32(450), i32(4500)),
        ('HealthComponentData', 309, 520 + 232, i32(450), i32(4500)),
    },
    'BastionReArmoredRecreation': bastion_writes(104) | bastion_writes(427),
    'FRVWeaponSwapRecreation': {
        ('MountComponentData', 19, 0, u64(0x085C1EDB038EC24E), u64(0x9872EEB31A5F88FD)),
        ('MountComponentData', 117, 0, u64(0x085C1EDB038EC24E), u64(0x9872EEB31A5F88FD)),
    },
    'JumpPackRecreation': {
        ('RechargeComponentData', 1, 0, f32(15), f32(8)),
        ('JumppackComponentData', 1, 0, f32(40), f32(50)),
    },
    'ConcussiveDrumMagazine': concussive_drum_writes(),
}
REFERENCES = {
    'ShieldRelayRecreation': ['ShieldRelayImprovements/scripts/shield_reference.py',
        'ShieldRelayImprovements/scripts/research/physical_hp_reference.py',
        'ShieldRelayImprovements/scripts/research/stratagem_patch.lua'],
    'BastionReArmoredRecreation': ['BastionReArmored/src/release/validate.lua',
        'BastionReArmored/src/armor_proof/validate.lua', 'BastionReArmored/src/lunchbox_proof/validate.lua'],
    'FRVWeaponSwapRecreation': ['FRVWeaponSwap/src/current_build.json', 'FRVWeaponSwap/src/frv_weapon_swap.lua'],
    'JumpPackRecreation': ['JumpPackImprovements/src/jump_pack_improvements.lua', 'JumpPackImprovements/src/config.lua'],
    'ConcussiveDrumMagazine': ['HD2Runtime/research/magazine-attachments-F5FEE03DCFDB.json'],
}


def lua(value): return json.dumps(str(value), ensure_ascii=False)


def sources():
    result = {}
    for folder in ('api', 'core', 'runtime', 'schemas', 'domains', 'primary_mapper'):
        for path in sorted((ROOT / folder).glob('*.lua')):
            result['hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()] = path.read_text()
    return result


def resolve(snapshot):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    addons = {name: (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text() for name in EXPECTED}
    table = '{' + ','.join('[' + lua(name) + ']=' + lua(body) for name, body in addons.items()) + '}'
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + lua(Path(snapshot).resolve()) + r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local plans=require('hd2runtime/domains/composition_plans')
local domains=require('hd2runtime/domains/write_domains')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local api=require('hd2runtime/api/hd2')
local function as_plan(request)
 if request.plan then return request.plan end
 local operation={}
 for key,value in pairs(request.patch)do operation[key]=value end
 return {id=operation.id,operations={operation}}
end
local wrapper=setmetatable({ensure=function(request)return plans.validate(as_plan(request))end,
 plan=function(request)return plans.validate(request)end},{__index=api})
package.preload['mods/skyeshade/hd2runtime']=function()return wrapper end
local addons=''' + table + r'''
local worker=coroutine.create(function()
 local result={}
 for name,body in pairs(addons)do
  local plan=assert(loadstring(body,name))()
  local writes={}
  for _,phase in ipairs(plan.phases)do
   local reader=Reader.new(source)
   local domain=domains.for_kind(phase.capture_specs[1].kind)
   local resolved=domain.capture_many(source,reader,phase.capture_specs)
   local prepared=plans.prepare_phase(resolved,reader,phase)
   reader.verify()
   for _,change in ipairs(prepared.changes)do
    writes[#writes+1]={component=change.identity.component,
     record=change.identity.component~='StratagemDefinition'and change.identity.record_index or nil,
     offset=change.field_offset,before=b.hex(change.before),after=b.hex(change.desired),
     alreadyDesired=change.already_desired,label=change.label}
   end
  end
  result[name]={phases=#plan.phases,operations=#plan.operations,writes=writes}
 end
 source.close()
 return result
end)
local ok,result
repeat ok,result=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,result);return json.encode(result)
'''
    return json.loads(execute(program.encode()))


def compare(resolved):
    report = {'mode': 'snapshot', 'snapshot': SNAPSHOT.name, 'researchWrites': 0, 'protectionChanges': 0,
        'fixtureFallback': 'disabled', 'recreations': {}}
    for name, expected in EXPECTED.items():
        item = resolved[name]
        actual = {(write['component'], write.get('record'), write['offset'], write['before'], write['after'])
            for write in item['writes']}
        if len(actual) != len(item['writes']):
            raise ValueError(name + ' produced duplicate physical writes')
        missing, unexpected = sorted(expected - actual, key=str), sorted(actual - expected, key=str)
        report['recreations'][name] = {'status': 'EXACT_MATCH' if not missing and not unexpected else 'MISMATCH',
            'phases': item['phases'], 'operations': item['operations'],
            'physicalWrites': len(actual), 'referenceWrites': len(expected),
            'allAtVanillaBaseline': not any(write['alreadyDesired'] for write in item['writes']),
            'missing': [list(entry) for entry in missing], 'unexpected': [list(entry) for entry in unexpected],
            'referenceSources': REFERENCES[name]}
    report['status'] = ('EXACT_MATCH' if all(entry['status'] == 'EXACT_MATCH'
        for entry in report['recreations'].values()) else 'MISMATCH')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = compare(resolve(args.snapshot))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({name: {k: v for k, v in entry.items() if k in ('status', 'physicalWrites', 'referenceWrites',
        'missing', 'unexpected')} for name, entry in report['recreations'].items()}, indent=2))
    if report['status'] != 'EXACT_MATCH':
        raise SystemExit('reference recreation mismatch')


if __name__ == '__main__':
    main()
