"""Validate every shipped example (example projects, live examples, the ModTemplate) against the current API.

For each example:

1. static: hd2runtime.json parses, and the Lua source uses no legacy fixed-resource API
   (the original short-name catalog, `hd2.observe`, `armor_penetration`, the old `weapon.default_fire_mode`);
2. API: the addon runs against the current runtime API with a validating adapter. Every hd2.patch /
   hd2.transaction / hd2.plan / hd2.ensure request is validated by the production write domains, so a
   field, target path, `expect` baseline or acknowledgement the SDK no longer accepts fails here;
3. minimum version: `requires.hd2runtime.min_version` is at least the oldest runtime that has every API the
   example uses (typed writes need 0.23.2, see docs/releases/0.23.2.md);
4. snapshot (unless --offline): every operation is resolved and prepared against the retained snapshot exactly as
   hd2.plan would prepare it, and every change's live bytes must equal its `expect` baseline. Nothing is written.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources

OUTPUT = ROOT / 'validation/example-projects.json'
TYPED_WRITES = '0.23.2'
# Oldest runtime for each feature an example can use (docs/releases/*).
FIELD_FLOORS = {
    **{field: '0.26.0' for field in ('attachment.reload_duration', 'attachment.ergonomics_modifier',
        'weapon.third_person_reticle', 'fire_mode.modes', 'fire_mode.burst_rounds', 'payload.entity',
        'payload.spawn_count', 'deposit.capacity', 'deposit.start_amount', 'deposit.refill_amount')},
    **{field: '0.24.0' for field in ('reload.duration', 'windup.wind_up_seconds', 'windup.wind_down_seconds',
        'projectile.lifetime', 'projectile.penetration_slowdown')},
}
# Floors that apply only in one write domain: max_uses on a plain stratagem is new in 0.26.0, while the
# booster's granted-stratagem max_uses has existed since 0.25.0.
KIND_FIELD_FLOORS = {('stratagem', 'stratagem.max_uses'): '0.26.0'}
RESOURCE_FLOORS = {'booster': '0.24.0', 'vehicle_weapon': '0.26.0', 'pod_rack': '0.26.0', 'throwable': '0.27.0'}
BOOSTER_PATH_FLOORS = {'tuning': '0.25.0', 'explosion': '0.25.0', 'status_damage': '0.25.0',
    'granted_stratagem': '0.25.0'}
DELIVERY_RESOLVED = {'MG-43 Machine Gun', 'M-105 Stalwart', 'MG-206 Heavy Machine Gun', 'CQC-20 Breaching Hammer'}
OPTIONS_FLOOR = '0.25.1'
LEGACY_PATTERNS = {
    r'fields\.damage\.armor_penetration': 'legacy JAR-5 armor_penetration; use damage.ap_direct/ap_slight/ap_large/ap_extreme',
    r'fields\.damage\.standard_damage\b': 'legacy standard_damage; use hd2.fields.damage.player_standard_damage',
    r'fields\.damage\.durable_damage\b': 'legacy durable_damage; use hd2.fields.damage.player_durable_damage',
    r':projectile\(\):damage\(\)': 'legacy fixed JAR-5 damage path; use weapon:attack(role):projectile()',
    r'hd2\.observe': 'legacy read-only observe on the original short-name catalog',
    r'default_fire_mode|enums\.fire_mode': 'older default-fire-mode enum; use hd2.fields.fire_mode.modes',
}


def version_key(value):
    return tuple(int(part) for part in value.split('.'))


def examples():
    found = [('ModTemplate', ROOT / 'starter')]
    # SDK project-generator templates (hd2.py new --template NAME); they get the current version.
    for path in sorted((ROOT / 'sdk/templates').iterdir()):
        if (path / 'addon.lua').is_file():
            found.append(('sdk-template-' + path.name, path))
    for folder in ('projects', 'live'):
        for path in sorted((ROOT / 'examples' / folder).iterdir()):
            if (path / 'hd2runtime.json').is_file():
                found.append((path.name, path))
    return found


PROGRAM = r'''
local api=require('hd2runtime/api/hd2')
local plans=require('hd2runtime/domains/composition_plans')
local domains=require('hd2runtime/domains/write_domains')
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local source
if SNAPSHOT_PATH then
 local profile=require('hd2runtime/schemas/current')
 source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
  expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
end
local ACK={allow_shared=true,allow_unverified_effect=true,allow_unverified_reference=true}
local function copy(value)
 if type(value)~='table'then return value end
 local out={};for key,item in pairs(value)do out[key]=item end;return setmetatable(out,getmetatable(value))
end
local function run_example(body,name)
 local report={operations={},usesOptions=false,calls={}}
 local function record(kind,request)
  report.calls[#report.calls+1]=kind
  local plan
  if request.plan then plan=request.plan
  elseif request.patch or request.transaction then
   local operation=copy(request.patch or request.transaction);plan={id=operation.id,operations={operation}}
  else error(kind..' request has no patch, transaction or plan',0)end
  local validated=plans.validate(plan)
  for _,phase in ipairs(validated.phases)do
   local family=domains.key_for_kind(phase.capture_specs[1].kind)
   for _,capture_spec in ipairs(phase.capture_specs)do
    assert(domains.key_for_kind(capture_spec.kind)==family,
     'one plan phase cannot mix stratagem, entity, and weapon targets (split them into phases)')
   end
  end
  local phases={}
  for _,phase in ipairs(validated.phases)do
   local specs={}
   for _,spec in ipairs(phase.capture_specs)do
    local fields={}
    for _,change in ipairs(spec.changes)do fields[#fields+1]=change.canonical_field or change.field end
    specs[#specs+1]={kind=spec.kind,fields=fields,assets=#(spec.asset_dependencies or{})}
   end
   phases[#phases+1]=specs
  end
  local operations={}
  for _,operation in ipairs(plan.operations or{})do operations[#operations+1]=operation end
  for _,phase in ipairs(plan.phases or{})do for _,operation in ipairs(phase.operations)do operations[#operations+1]=operation end end
  for _,operation in ipairs(operations)do
   local target=operation.target or{}
   local acks={};for key in pairs(ACK)do if operation[key]then acks[#acks+1]=key end end;table.sort(acks)
   local weapon=rawget(target,'weapon')
   report.operations[#report.operations+1]={id=operation.id,resource=rawget(target,'resource'),
    path=rawget(target,'path'),weapon=type(weapon)=='string'and weapon or nil,acknowledgements=acks,
    mode=operation.changes and'transaction'or'patch',callKind=kind}
  end
  report.phases=report.phases or{}
  for _,phase in ipairs(phases)do report.phases[#report.phases+1]=phase end
  if source then
   for _,phase in ipairs(validated.phases)do
    local reader=Reader.new(source)
    local domain=domains.for_kind(phase.capture_specs[1].kind)
    local resolved=domain.capture_many(source,reader,phase.capture_specs)
    local prepared=plans.prepare_phase(resolved,reader,phase)
    reader.verify()
    for _,change in ipairs(prepared.changes)do
     assert(change.before==change.expected,name..': live value of '..tostring(change.label)
      ..' differs from its expect baseline')
     report.baselineChanges=(report.baselineChanges or 0)+1
    end
   end
  end
  return {validated=true}
 end
 local function options_page(spec)
  report.usesOptions=true
  local page={}
  local function control(item)return item.default end
  page.slider=function(_,item)return control(item)end
  page.toggle=function(_,item)return control(item)end
  page.choice=function(_,item)return control(item)end
  return page
 end
 local wrapper=setmetatable({
  patch=function(request)return record('patch',{patch=request})end,
  transaction=function(request)return record('transaction',{transaction=request})end,
  plan=function(request)return record('plan',{plan=request})end,
  ensure=function(request)
   local stripped={patch=request.patch,transaction=request.transaction,plan=request.plan}
   return record('ensure',stripped)
  end,
  options=options_page},{__index=api})
 package.loaded['mods/skyeshade/hd2runtime']=wrapper
 package.preload['mods/skyeshade/hd2runtime']=function()return wrapper end
 local chunk=assert(loadstring(body,name))
 chunk()
 return report
end
local worker=coroutine.create(function()
 local result={}
 for name,body in pairs(EXAMPLES)do
  local ok,report=pcall(run_example,body,name)
  if ok then report.status='VALIDATED' else report={status='FAILED',error=tostring(report)} end
  result[name]=report
 end
 if source then source.close()end
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def required_version(report):
    need = TYPED_WRITES if report.get('operations') else '0.1.0'
    reasons = []

    def bump(value, reason):
        nonlocal need
        if version_key(value) > version_key(need):
            need = value
        reasons.append(reason + ' -> ' + value)
    if report.get('operations'):
        reasons.append('typed writes -> ' + TYPED_WRITES)
    if report.get('usesOptions'):
        bump(OPTIONS_FLOOR, 'in-game options')
    for operation in report.get('operations', []):
        resource, path = operation.get('resource'), operation.get('path')
        if resource in RESOURCE_FLOORS:
            bump(RESOURCE_FLOORS[resource], resource + ' target')
        if resource == 'booster' and path in BOOSTER_PATH_FLOORS:
            bump(BOOSTER_PATH_FLOORS[path], 'booster ' + path + '()')
        if resource == 'support_weapon' and operation.get('weapon') in DELIVERY_RESOLVED:
            bump('0.24.0', operation['weapon'])
    for phase in report.get('phases', []):
        for spec in phase:
            for field in spec['fields']:
                generic = re.sub(r'^(projectile|damage|explosion)\.(primary|alternate|impact|expiry)\.', r'\1.', field)
                if generic in FIELD_FLOORS:
                    bump(FIELD_FLOORS[generic], field)
                if (spec['kind'], field) in KIND_FIELD_FLOORS:
                    bump(KIND_FIELD_FLOORS[(spec['kind'], field)], spec['kind'] + ' ' + field)
    return need, sorted(set(reasons))


def validate(snapshot=SNAPSHOT, offline=False):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    found = examples()
    bodies = {name: ((path / 'src/addon.lua') if (path / 'src/addon.lua').is_file() else path / 'addon.lua')
        .read_text(encoding='utf-8') for name, path in found}
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    table = '{' + ','.join('[' + lua(name) + ']=' + lua(body) for name, body in bodies.items()) + '}'
    program = (preload + '\nlocal SNAPSHOT_PATH=' + ('nil' if offline else lua(Path(snapshot).resolve()))
        + '\nlocal EXAMPLES=' + table + '\n' + PROGRAM)
    dynamic = json.loads(execute(program.encode()))
    results = {}
    for name, path in found:
        if (path / 'hd2runtime.json').is_file():
            declared = json.loads((path / 'hd2runtime.json').read_text())['requires']['hd2runtime']['min_version']
        else:
            declared = (ROOT / 'VERSION').read_text().strip()
        report = dynamic[name]
        problems = [] if report['status'] == 'VALIDATED' else [report.get('error')]
        for pattern, reason in LEGACY_PATTERNS.items():
            if re.search(pattern, bodies[name]):
                problems.append('teaches ' + reason)
        need, reasons = required_version(report) if report['status'] == 'VALIDATED' else (None, [])
        if need and version_key(declared) < version_key(need):
            problems.append(f'min_version {declared} is below the required {need} ({"; ".join(reasons)})')
        results[name] = {'status': 'VALIDATED' if not problems else 'FAILED', 'problems': problems,
            'minVersion': declared, 'requiredMinVersion': need, 'versionReasons': reasons,
            'calls': sorted(set(report.get('calls', []))), 'operations': report.get('operations', []),
            'baselineChanges': report.get('baselineChanges'), 'usesOptions': report.get('usesOptions', False)}
    failed = sorted(name for name, item in results.items() if item['status'] != 'VALIDATED')
    return {'status': 'VALIDATED' if not failed else 'FAILED', 'mode': 'offline' if offline else 'snapshot',
        'snapshot': None if offline else Path(snapshot).name, 'examples': len(results), 'failed': failed,
        'writes': 0, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--offline', action='store_true', help='API validation only; skip snapshot baselines')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot, args.offline)
    if not args.offline:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', newline='\n')
    for name, item in sorted(result['results'].items()):
        print(('ok   ' if item['status'] == 'VALIDATED' else 'FAIL ') + name + ' min=' + item['minVersion']
            + ' need=' + str(item['requiredMinVersion']) + ('' if not item['problems'] else ' :: ' + ' | '.join(item['problems'])))
    print(result['status'], len(result['failed']), 'failed of', result['examples'])
    if result['status'] != 'VALIDATED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
