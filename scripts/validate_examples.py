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
# New in 0.28.0 (docs/releases/0.28.0.md). The field sets are the catalog diff against v0.27.0 (normalized like the
# fields below), plus members 0.27.0 published but not writable: status slots on player-weapon projectiles. Every
# example these floors mark was also checked to fail validation against the v0.27.0 runtime.
RELEASE_0_28_0 = '0.28.0'
RELEASE_0_28_1 = '0.28.1'   # hd2.diagnostics.operations()
FIELDS_0_28_0 = {'weapon.stationary_while_firing', 'weapon.recoil_multiplier_horizontal',
    'weapon.recoil_multiplier_vertical', 'beam.fire_rate',
    # Equipment coverage (research/equipment-coverage-F5FEE03DCFDB.json).
    'shield.recharge_delay', 'shield.broken_recharge_delay', 'shield.recharge_rate', 'hover.duration',
    'warp.distance', 'warp.upward_bias', 'warp.downward_bias', 'warp.safe_heat_threshold', 'warp.unsafe_heat_threshold',
    'warp.heat_per_use', 'warp.heat_cooldown_per_second', 'warp.head_injury_damage', 'warp.left_arm_injury_damage',
    'warp.right_arm_injury_damage', 'warp.left_leg_injury_damage', 'warp.right_leg_injury_damage',
    'heat.level_1_threshold', 'heat.level_2_threshold', 'heat.level_3_threshold', 'heat.level_1_self_status',
    'heat.level_2_self_status', 'heat.level_3_self_status', 'heat.overheat_lock',
    # Rate-of-fire modes, weapon functions and feeds, programmable ammo, armory presentation.
    'fire_rate.modes', 'weapon_function.left', 'weapon_function.right', 'function_ammo.projectile',
    'presentation.armor_penetration', 'presentation.traits', 'presentation.mode_label', 'presentation.mode_icon',
    # The unified projectile system: ammunition sources and projectile builder slots.
    'ammunition.projectile', 'projectile.direct_damage', 'projectile.impact_explosion', 'projectile.expiry_explosion',
    # Sentries and minefields.
    'turret.yaw_speed', 'turret.pitch_speed', 'turret.yaw_min', 'turret.yaw_max', 'turret.pitch_min',
    'turret.pitch_max', 'targeting.range', 'minefield.salvos', 'minefield.mines_per_salvo'}
STATUS_SLOTS = {prefix + 'status_%d_%s' % (slot, part) for prefix in ('damage.', 'explosion.damage.')
    for slot in (1, 2, 3, 4) for part in ('type', 'strength')}
KIND_FIELDS_0_28_0 = {
    'player_weapon': {'projectile.lifetime', 'projectile.penetration_slowdown'} | STATUS_SLOTS,
    'support_weapon': {'attack.projectile'} | STATUS_SLOTS,
    'vehicle_weapon': {'attack.primary.projectile', 'arc.primary.chain_count', 'arc.primary.distance_at_max_spread',
        'arc.primary.max_angle_spread', 'arc.primary.max_split', 'arc.primary.range', 'arc.primary.velocity',
        'beam.primary.length', 'beam.primary.radius', 'heat.capacity', 'heat.cool_per_second', 'heat.heat_per_shot'}
        | STATUS_SLOTS}
RESOURCE_FLOORS = {'booster': '0.24.0', 'vehicle_weapon': '0.26.0', 'pod_rack': '0.26.0', 'throwable': '0.27.0',
    'enemy': RELEASE_0_28_0, 'attack_output': RELEASE_0_28_0}
RESOURCE_PATH_FLOORS = {('backpack', 'damage_zone'): RELEASE_0_28_0, ('player_weapon', 'ammunition'): RELEASE_0_28_0}
BOOSTER_PATH_FLOORS = {'tuning': '0.25.0', 'explosion': '0.25.0', 'status_damage': '0.25.0',
    'granted_stratagem': '0.25.0'}
DELIVERY_RESOLVED = {'MG-43 Machine Gun', 'M-105 Stalwart', 'MG-206 Heavy Machine Gun', 'CQC-20 Breaching Hammer'}
SUPPORT_WEAPONS_0_28_0 = {'EAT-17 Expendable Anti-Tank', 'LAS-98 Laser Cannon', 'B/FLAM-80 Cremator'}
STRATAGEM_WEAPONS_0_28_0 = {'mine'}   # a mine deployer's launcher owns its mine attacks
# Features not in any published release yet need the release that ships them, i.e. the version being built. Empty
# right after a release; the next release pins them like the 0.28.0 sets above.
UNRELEASED = (ROOT / 'VERSION').read_text().strip()
UNRELEASED_FIELDS = {'stratagem.calldown_code',   # docs/stratagem-calldown-code.md
    'stratagem.presentation.name', 'stratagem.presentation.name_cased', 'stratagem.presentation.description',
    'stratagem.presentation.icon',                  # docs/stratagem-presentation.md
    'gore.whole_body_gib_damage'}                   # docs/enemy-authoring.md (whole-body gib threshold)
# Charge (docs/support-weapon-api.md "Charge") and jump / hover movement (docs/backpack-authoring.md).
UNRELEASED_FIELDS |= {'charge.speed_multiplier_min', 'charge.speed_multiplier_overcharge', 'charge.damage_multiplier_min',
    'charge.damage_multiplier_overcharge', 'charge.penetration_multiplier_min', 'charge.penetration_multiplier_overcharge',
    'charge.arc_distance_multiplier_min', 'charge.arc_distance_multiplier_overcharge', 'charge.auto_fire_at_full',
    'charge.explode_at_overcharge', 'charge.overcharge_explosion', 'charge.overcharge_limit_seconds', 'charge.burst_shots',
    'charge.burst_interval_seconds', 'jump.launch_duration', 'jump.launch_forward_ratio', 'jump.sustain_thrust',
    'jump.sustain_duration', 'jump.sustain_forward_ratio', 'jump.sustain_start_delay', 'jump.sustain_start_speed',
    'jump.sustain_cutoff_speed', 'jump.air_control_acceleration', 'jump.air_control_max_speed', 'jump.takeoff_forward_speed',
    'jump.takeoff_speed', 'jump.takeoff_speed_alternate_stance', 'hover.max_horizontal_speed', 'hover.max_vertical_speed',
    'hover.vertical_acceleration_low_speed', 'hover.vertical_acceleration_high_speed', 'hover.vertical_speed_range_end',
    'hover.fuel_rate_low_speed', 'hover.fuel_rate_high_speed'}
# Vehicle tuning (docs/vehicle-authoring.md, docs/vehicle-weapons.md): Exosuit body rotation and steering are new ids;
# the turret ids already shipped for sentries (0.28.0) but are new on mounted weapons.
UNRELEASED_FIELDS |= {'rotation.turn_speed', 'rotation.acceleration', 'rotation.deceleration',
    'vehicle.steering_response_speed'}
KIND_FIELD_FLOORS.update({('vehicle_weapon', 'turret.' + name): UNRELEASED for name in ('yaw_speed', 'pitch_speed',
    'pitch_min', 'pitch_max', 'yaw_min', 'yaw_max')})
# Sentry component fields (docs/stratagem-authoring.md "Sentry turret motion, targeting and weapon handling"): three new
# ids, and player/support weapon ids that are new on a sentry's deployed entity.
UNRELEASED_FIELDS |= {'turret.pitch_yaw_coupling', 'targeting.side_range', 'targeting.rear_range'}
# Orbital bombardment pattern and call-in time (docs/stratagem-authoring.md "Orbital bombardment pattern", "Call-in time").
UNRELEASED_FIELDS |= {'orbital.salvos', 'orbital.shells_per_salvo', 'orbital.shell_interval',
    'orbital.shell_interval_random', 'orbital.salvo_interval', 'orbital.salvo_interval_random', 'orbital.scatter',
    'orbital.salvo_scatter', 'stratagem.call_in_time'}
# Support attack roles new in this line (docs/support-weapon-api.md, research/charge-explosions-F5FEE03DCFDB.json): the
# PLAS-45 Epoch's full-charge shot and its explosion, and the Epoch's and the RS-422 Railgun's overcharge explosions.
SUPPORT_ROLES_UNRELEASED = {'full_charge', 'full_charge_impact', 'overcharge_explosion'}
# Eagle attack fields, Phase A (docs/stratagem-authoring.md "Eagle attack fields"): new in this line.
UNRELEASED_FIELDS |= {'eagle.airstrike_pattern', 'eagle.drop_interval', 'eagle.fire_duration',
    'eagle.attack_sweep_length', 'eagle.target_radius', 'eagle.attack_angle'}
KIND_FIELD_FLOORS.update({('stratagem', field): UNRELEASED for field in ('weapon.horizontal_spread',
    'weapon.vertical_spread', 'weapon.recoil_drift_horizontal', 'weapon.recoil_drift_vertical',
    'weapon.recoil_climb_horizontal', 'weapon.recoil_climb_vertical', 'windup.wind_up_seconds',
    'windup.wind_down_seconds', 'beam.fire_rate')})
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
    """SemVer precedence: MAJOR.MINOR.PATCH, then a prerelease (e.g. 0.30.0-dev) below its release; +build ignored."""
    core, _, pre = value.split('+')[0].partition('-')
    major, minor, patch = (int(part) for part in core.split('.'))
    if not pre:
        return (major, minor, patch, 1, ())
    return (major, minor, patch, 0, tuple((0, int(p), '') if p.isdigit() else (1, 0, p) for p in pre.split('.')))


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
local options_module=require('hd2runtime/api/options')
local function copy(value)
 if type(value)~='table'then return value end
 local out={};for key,item in pairs(value)do out[key]=item end;return setmetatable(out,getmetatable(value))
end
-- Bound values (script values from mod:value) validate with their current value, as a live ensure does first.
local function materialize(value,depth)
 if options_module.is_handle(value)then return value:get()end
 if type(value)~='table'or getmetatable(value)~=nil or(depth or 0)>16 then return value end
 local out={};for key,item in pairs(value)do out[key]=materialize(item,(depth or 0)+1)end;return out
end
local function run_example(body,name)
 local report={operations={},usesOptions=false,calls={}}
 report.usesOperationList=body:find('diagnostics%.operations')~=nil
 report.usesHoming=body:find('projectiles%.homing')~=nil
 report.usesSpawnWeights=body:find('enemies%.spawn_')~=nil
 report.usesMoreDonors=body:find('%(projectile %d+%)')~=nil
 report.usesEvents=body:find('hd2%.events')~=nil or body:find('hd2%.mod%(')~=nil or body:find('hd2%.after')~=nil
  or body:find('hd2%.every')~=nil or body:find('hd2%.input')~=nil
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
    local requested={}
    for _,change in ipairs(spec.changes)do
     fields[#fields+1]=change.canonical_field or change.field;requested[#requested+1]=tostring(change.field)
    end
    specs[#specs+1]={kind=spec.kind,fields=fields,requested=requested,assets=#(spec.asset_dependencies or{})}
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
   local attack=rawget(target,'attack')
   report.operations[#report.operations+1]={id=operation.id,resource=rawget(target,'resource'),
    path=rawget(target,'path'),weapon=type(weapon)=='string'and weapon or nil,acknowledgements=acks,
    attack=type(attack)=='string'and attack or nil,mode=operation.changes and'transaction'or'patch',callKind=kind}
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
  -- A choice's value is values[default] (the index when values is omitted), as the real options API returns.
  page.choice=function(_,item)
   local index=item.default or 1
   return item.values and item.values[index]or index
  end
  return page
 end
 local wrapper=setmetatable({
  patch=function(request)return record('patch',{patch=request})end,
  transaction=function(request)return record('transaction',{transaction=request})end,
  plan=function(request)return record('plan',{plan=request})end,
  ensure=function(request)
   local stripped=materialize({patch=request.patch,transaction=request.transaction,plan=request.plan})
   return record('ensure',stripped)
  end,
  options=options_page},{__index=api})
 package.loaded['mods/skyeshade/hd2runtime']=wrapper
 package.preload['mods/skyeshade/hd2runtime']=function()return wrapper end
 local chunk=assert(loadstring(body,name))
 -- As the SDK addon wrapper runs it: the startup runs as the mod's own resource id (automatic ownership).
 local resource=RESOURCES[name]
 if resource and api.events and api.events.run_as then api.events.run_as(resource,chunk)else chunk()end
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
    if report.get('usesOperationList'):
        bump(RELEASE_0_28_1, 'hd2.diagnostics.operations()')
    if report.get('usesHoming'):
        bump(UNRELEASED, 'hd2.projectiles.homing')
    if report.get('usesSpawnWeights'):
        bump(UNRELEASED, 'hd2.enemies spawn weights')
    if report.get('usesMoreDonors'):
        bump(UNRELEASED, 'more projectile donors (docs/attack-outputs.md)')
    if report.get('usesEvents'):
        bump(RELEASE_0_28_0, 'gameplay scripting (hd2.events, hd2.mod, timers, keybinds)')
    for operation in report.get('operations', []):
        resource, path = operation.get('resource'), operation.get('path')
        if resource in RESOURCE_FLOORS:
            bump(RESOURCE_FLOORS[resource], resource + ' target')
        if (resource, path) in RESOURCE_PATH_FLOORS:
            bump(RESOURCE_PATH_FLOORS[(resource, path)], resource + ' ' + path)
        if resource == 'player_weapon' and ' / underbarrel' in (operation.get('weapon') or ''):
            bump(RELEASE_0_28_0, 'underbarrel sub-target')
        if resource == 'booster' and path in BOOSTER_PATH_FLOORS:
            bump(BOOSTER_PATH_FLOORS[path], 'booster ' + path + '()')
        if resource == 'support_weapon' and operation.get('weapon') in DELIVERY_RESOLVED:
            bump('0.24.0', operation['weapon'])
        if resource == 'support_weapon' and operation.get('weapon') in SUPPORT_WEAPONS_0_28_0:
            bump(RELEASE_0_28_0, operation['weapon'] + ' (structurally delivery-resolved)')
        if resource == 'stratagem' and operation.get('weapon') in STRATAGEM_WEAPONS_0_28_0:
            bump(RELEASE_0_28_0, 'stratagem mine explosion')
        if resource == 'support_weapon' and operation.get('attack') in SUPPORT_ROLES_UNRELEASED:
            bump(UNRELEASED, 'support attack role ' + operation['attack'])
    for phase in report.get('phases', []):
        for spec in phase:
            for index, field in enumerate(spec['fields']):
                generic = re.sub(r'^(projectile|damage|explosion)\.(primary|alternate|impact|expiry)\.', r'\1.', field)
                if generic in FIELD_FLOORS:
                    bump(FIELD_FLOORS[generic], field)
                if generic in FIELDS_0_28_0 or field in KIND_FIELDS_0_28_0.get(spec['kind'], ()) \
                        or generic in KIND_FIELDS_0_28_0.get(spec['kind'], ()):
                    bump(RELEASE_0_28_0, spec['kind'] + ' ' + field)
                # A generic projectile field resolved to a rounds-feed branch (the SG-20 Halt): 0.27.0 refused it.
                requested = (spec.get('requested') or [])[index:index + 1]
                if spec['kind'] == 'player_weapon' and generic != field and requested == [generic]:
                    bump(RELEASE_0_28_0, field + ' through the generic ' + generic)
                if generic in UNRELEASED_FIELDS:
                    bump(UNRELEASED, field)
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
    resources = {name: json.loads((path / 'hd2runtime.json').read_text(encoding='utf-8'))['resource']
        for name, path in found if (path / 'hd2runtime.json').is_file()}
    program = (preload + '\nlocal SNAPSHOT_PATH=' + ('nil' if offline else lua(Path(snapshot).resolve()))
        + '\nlocal EXAMPLES=' + table + '\nlocal RESOURCES={'
        + ','.join('[' + lua(name) + ']=' + lua(resource) for name, resource in resources.items()) + '}\n' + PROGRAM)
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
