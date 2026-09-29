"""Exercise attack-output composition through the production player-weapon write domain on the retained snapshot.

On a copy-on-write memory overlay of the snapshot (no game process, no real writes), with the AR-23 Liberator as
the host:

- Vanilla (the Liberator's own projectile) resolves as an already-desired no-op.
- EAT-700 napalm rocket, GL-52 De-Escalator arc grenade (cross-class) and LAS-58 Talon (same class) outputs: the host
  ProjectileWeapon +0 reference changes to the output's projectile, nothing else in the host record moves, the
  output's package is declared as the asset dependency, and the guarded inverse restores the exact baseline.
- A plain patch finding another output live is a CONFLICT (only an ensure that owns the value may transition).
- Rejections: beam (LAS-98, Trident) and arc (ARC-3) outputs (INCOMPATIBLE_OUTPUT_FAMILY), missing
  allow_unverified_reference / allow_unverified_effect, a non-host weapon, a stale output source and a host whose
  magazine pattern starts selecting other projectiles.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources  # noqa: E402
import validate_attachment_authoring_snapshot as overlay_source  # noqa: E402

OUTPUT = ROOT / 'validation/attack-output-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local weapons=require('hd2runtime/domains/player_weapon_writes')
local outputs=require('hd2runtime/domains/attack_outputs')
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=weapons.capture(runtime,reader,spec)
 local plan=weapons.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local HOST='AR-23 Liberator'
local host={resource='player_weapon',path='attack',weapon=HOST,attack='primary'}
local own={resource='player_weapon',path='projectile_reference',weapon=HOST,attack='primary'}
local function output(name)return {resource='attack_output',output=outputs.aliases[name]}end
local function patch(value,extra)
 local request={id='attack-output',target=host,field='attack.projectile',expect=own,value=value,
  allow_unverified_reference=true,allow_unverified_effect=true}
 for k,v in pairs(extra or{})do if v==false then request[k]=nil else request[k]=v end end
 return weapons.validate_patch(request)
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 host=HOST,compositions={},rejections={}}
local worker=coroutine.create(function()
 -- Vanilla: the host's own projectile is already live.
 local plan=resolve(patch(own,{allow_unverified_reference=false,allow_unverified_effect=false}))
 assert(#plan.changes==1 and plan.changes[1].already_desired,'vanilla is not the live baseline')
 local baseline=plan.changes[1].before
 result.baselineProjectile=b.u32(baseline,0)
 -- Each output: apply, read back, untouched neighbours, exact rollback.
 for _,name in ipairs({'EAT-700 Expendable Napalm','GL-52 De-Escalator','LAS-58 Talon'})do
  reset()
  local entry=outputs.outputs[outputs.aliases[name]]
  local spec=patch(output(name))
  local plan=resolve(spec)
  local part=plan.changes[1]
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,name..' write failed')
  assert(runtime.read(part.owner.base+part.offset,4)==b.encode(entry.currentDefault,'u32'),name..' did not land')
  -- A plain patch that finds a different output live is a conflict (only an owning ensure may transition).
  local other=name=='EAT-700 Expendable Napalm'and'GL-52 De-Escalator'or'EAT-700 Expendable Napalm'
  rejects(function()resolve(patch(output(other)))end,'CONFLICT',name..' ownership conflict')
  assert(guarded.apply(runtime,guarded.inverse(plan)).status=='APPLIED',name..' rollback failed')
  assert(runtime.read(part.owner.base+part.offset,4)==baseline,name..' rollback did not restore the baseline')
  local dependency=spec.asset_dependencies and spec.asset_dependencies[1]
  result.compositions[name]={output=entry.id,class=entry.compatibilityClass,crossClass=spec.changes[1].cross_class,
   projectile=entry.currentDefault,package=dependency and dependency.name or nil,writes=applied.writes}
 end
 reset()
 -- Cross-family outputs have no projectile reference to write.
 for _,name in ipairs({'LAS-98 Laser Cannon','LAS-13 Trident','ARC-3 Arc Thrower'})do
  rejects(function()patch(output(name))end,'INCOMPATIBLE_OUTPUT_FAMILY',name)
  result.rejections[name]='INCOMPATIBLE_OUTPUT_FAMILY'
 end
 rejects(function()patch(output('EAT-700 Expendable Napalm'),{allow_unverified_reference=false})end,
  'allow_unverified_reference','cross-class reference acknowledgement')
 rejects(function()patch(output('EAT-700 Expendable Napalm'),{allow_unverified_effect=false})end,
  'allow_unverified_effect','cross-class effect acknowledgement')
 result.rejections.acknowledgements=2
 -- A projectile weapon whose rounds are not all its projectile reference cannot host cross-class outputs.
 local non_host
 for weapon_name,weapon in pairs(require('hd2runtime/domains/player_weapon_authoring').weapons)do
  if not outputs.hosts[weapon_name]and not weapon.ordinaryWritesBlocked then
   for _,field in ipairs(weapon.fields)do
    if field.semanticFieldId=='attack.primary.projectile'and field.editable and field.backing then
     non_host=non_host or weapon_name
    end
   end
  end
 end
 rejects(function()weapons.validate_patch({id='x',target={resource='player_weapon',path='attack',weapon=non_host,
  attack='primary'},field='attack.projectile',expect={resource='player_weapon',path='projectile_reference',
  weapon=non_host,attack='primary'},value=output('EAT-700 Expendable Napalm'),allow_unverified_reference=true,
  allow_unverified_effect=true})end,'CROSS_CLASS_HOST_REJECTED','non-host weapon')
 result.rejections.nonHost=non_host
 -- Stale output source: the EAT-700's own reference no longer names the catalogued projectile.
 local spec=patch(output('EAT-700 Expendable Napalm'))
 local _,resolved=resolve(spec)
 local source_record=resolved.catalog.record(resolved.reference_sources[spec.changes[1].canonical_field],
  'ProjectileWeaponComponentData')
 poke(source_record.owner.base+source_record.offset,b.encode(276,'u32'))
 rejects(function()resolve(spec)end,'source projectile reference changed','stale output source')
 reset()
 -- Host proof: a magazine pattern entry would select other projectiles for some rounds.
 local _,resolved2=resolve(spec)
 local magazine=resolved2.catalog.record(resolved2.candidate,'WeaponMagazineComponentData')
 poke(magazine.owner.base+magazine.offset+4,b.encode(7,'u32'))
 rejects(function()resolve(spec)end,'CROSS_CLASS_HOST_REJECTED','host magazine pattern')
 result.rejections.staleSource=1;result.rejections.hostMagazinePattern=1
 reset()
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def validate(snapshot):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\n' + PROGRAM)
    return json.loads(execute(program.encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', newline='\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
