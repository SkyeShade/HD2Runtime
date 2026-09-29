"""Exercise mounted-weapon fields and stratagem mission uses on a copy-on-write snapshot overlay.

Mounted weapons (vehicles, Exosuits, GATER): every writable field of every reviewed mount is

1. applied as a guarded no-op (ALREADY_DESIRED, no writes),
2. changed, read back, and rolled back exactly,
3. rejected as CONFLICT when a third party changed the bytes first,
4. rejected without allow_shared (shared scopes) or allow_unverified_effect (not gameplay-proven).

A moved mount (the vehicle's MountComponentData slot no longer names the weapon) is rejected.

Stratagem mission uses (StratagemInfo +80): every writable stratagem is checked with a no-op, its
transition (finite -> unlimited, unlimited -> finite, finite -> different finite) with read-back and
rollback, a conflict, and the acknowledgement rule. Unlimited is always the native 0xFFFFFFFF value.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources
import validate_attachment_authoring_snapshot as overlay_source
import parallel  # noqa: E402
import sharded_validation  # noqa: E402

OUTPUT = ROOT / 'validation/vehicle-weapon-authoring-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local weapons=require('hd2runtime/domains/player_weapon_writes')
local vehicles=require('hd2runtime/domains/vehicle_weapon_authoring')
local stratagems=require('hd2runtime/domains/stratagem_writes')
local strat_db=require('hd2runtime/domains/stratagem_authoring')
local function resolve(domain,spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan,resolved
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
-- Public field ids omit the attack role (projectile.primary.velocity -> projectile.velocity).
local function public_id(field)
 local role=field.target.attack
 if not role then return field.semanticFieldId end
 return (field.semanticFieldId:gsub('^(%a+)%.'..role..'%.','%1.'))
end
local status_catalog=require('hd2runtime/domains/status_catalog')
local function changed_value(field)
 local value=field.currentDefault
 if field.type=='status_reference'then
  -- Another attachable status (a used slot) or the first one (the empty attachment slot).
  for _,candidate in ipairs(field.allowedValues)do if candidate~=value then return candidate end end
 end
 if field.type=='integer'then return value+1 end
 return value==0 and 1 or value*1.25
end
-- A third-party value that is neither the reviewed nor the desired bytes.
local function third_party(field)
 if field.type=='status_reference'then return b.encode(9999,'u32')end
 return b.encode(field.currentDefault+7,field.backing.storage)
end
local function round_trip(domain,spec,label)
 local plan=resolve(domain,spec)
 local changed=0
 for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==changed and applied.non_target_bytes_unchanged,
  label..' write failed: '..tostring(applied.reason))
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,label..' write did not land')
 end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED',label..' rollback failed')
 for _,part in ipairs(plan.changes)do
  assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,label..' rollback did not restore')
 end
 return plan,applied
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 vehicleWeapons=0,vehicleFields=0,noOps=0,changedWrites=0,rollbacks=0,conflictRejections=0,
 sharedRejections=0,acknowledgementRejections=0,mountChainRejections=0,byScope={},
 stratagemUses={checked=0,transitions={},proven=0,acknowledgementRejections=0,conflictRejections=0},
 scenarios={}}
local worker=coroutine.create(function()
 local names={};for name in pairs(vehicles.weapons)do names[#names+1]=name end;table.sort(names)
 names=shard(names)
 for _,name in ipairs(names)do
  local weapon=vehicles.weapons[name]
  result.vehicleWeapons=result.vehicleWeapons+1
  for _,field in ipairs(weapon.fields)do if field.editable then
   local label=name..' '..field.semanticFieldId
   local shared=field.affectsMultipleWeapons or(field.target.path=='projectile_reference'and field.backing.kind=='settings')
   local ack=field.acknowledgement=='allow_unverified_effect'
   local function request(expect,value,with_shared,with_ack)
    return {id='vehicle-weapon-check',target=field.target,field=public_id(field),expect=expect,value=value,
     allow_shared=with_shared or nil,allow_unverified_effect=with_ack or nil}
   end
   reset()
   local plan=resolve(weapons,weapons.validate_patch(request(field.currentDefault,field.currentDefault,shared,ack)))
   local checked=guarded.apply(runtime,plan)
   assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,label..' no-op changed state')
   result.noOps=result.noOps+1
   local value=changed_value(field)
   local spec=weapons.validate_patch(request(field.currentDefault,value,shared,ack))
   plan=round_trip(weapons,spec,label)
   result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
   local part=plan.changes[1]
   poke(part.owner.base+part.offset,third_party(field))
   rejects(function()resolve(weapons,spec)end,'CONFLICT',label..' conflict')
   result.conflictRejections=result.conflictRejections+1
   reset()
   if shared then
    rejects(function()weapons.validate_patch(request(field.currentDefault,value,nil,ack))end,'allow_shared',
     label..' without allow_shared')
    result.sharedRejections=result.sharedRejections+1
   end
   if ack then
    rejects(function()weapons.validate_patch(request(field.currentDefault,value,shared,nil))end,
     'allow_unverified_effect',label..' without allow_unverified_effect')
    result.acknowledgementRejections=result.acknowledgementRejections+1
   end
   result.vehicleFields=result.vehicleFields+1
   result.byScope[field.writeScope]=(result.byScope[field.writeScope]or 0)+1
  end end
  -- The mount chain is re-proven: a vehicle whose slot no longer holds this weapon is rejected.
  local first
  for _,field in ipairs(weapon.fields)do if field.editable and field.target.path=='weapon'then first=field;break end end
  if first then
   reset()
   local spec=weapons.validate_patch({id='mount-chain',target=first.target,field=public_id(first),
    expect=first.currentDefault,value=first.currentDefault,allow_shared=first.affectsMultipleWeapons or nil,
    allow_unverified_effect=first.acknowledgement and true or nil})
   local _,resolved=resolve(weapons,spec)
   local chain=weapon.mountChain;local vehicle
   for _,candidate in ipairs(resolved.catalog.candidates)do
    if candidate.resourceHash==chain.vehicleResource then vehicle=candidate end end
   local mount=resolved.catalog.record(vehicle,'MountComponentData')
   poke(mount.owner.base+mount.offset+chain.slot*24,string.rep('\0',8))
   rejects(function()resolve(weapons,spec)end,'vehicle mount chain changed',name..' moved mount')
   result.mountChainRejections=result.mountChainRejections+1
   reset()
  end
 end
 if EXTRAS then
 -- Explicit scenarios: FRV mounted gun, tank main cannon, tank MG, Exosuit arms.
 local function scenario(key,weapon,field,expect,value,options)
  reset()
  local target=hd2_target(weapon,field)
  local request={id=key,target=target.target,field=public_id(target),expect=expect,value=value}
  for option,flag in pairs(options or{})do request[option]=flag end
  local plan,applied=round_trip(weapons,weapons.validate_patch(request),key)
  local part=plan.changes[1]
  result.scenarios[key]={weapon=weapon,field=field,from=expect,to=value,component=part.identity.component,
   before=b.hex(part.before),after=b.hex(part.desired),writes=applied.writes,uniqueOwner=part.identity.unique_owner}
 end
 function hd2_target(weapon,field)
  for _,item in ipairs(vehicles.weapons[weapon].fields)do
   if item.semanticFieldId==field then return item end
  end
  error('no field '..field..' on '..weapon)
 end
 scenario('frv_gun_capacity','M-103 Supply FRV / gun','weapon.capacity',120,600)
 scenario('bastion_cannon_damage','TD-220 Bastion MK XVI / attach_tank_gun','damage.primary.standard_damage',3500,5000,
  {allow_shared=true,allow_unverified_effect=true})
 scenario('bastion_cannon_reserve','TD-220 Bastion MK XVI / attach_tank_gun','magazine.spare_magazines',30,45,
  {allow_unverified_effect=true})
 scenario('bastion_mg_capacity','TD-220 Bastion MK XVI / attach_tank_gun_mg','weapon.capacity',2000,3000,
  {allow_unverified_effect=true})
 scenario('maelstrom_gun_fire_rate','TD-110 Maelstrom / attach_tank_gun','weapon.fire_rate',1200,900,
  {allow_unverified_effect=true})
 scenario('emancipator_left_capacity','EXO-49 Emancipator Exosuit / left_gun','weapon.capacity',100,150)
 scenario('emancipator_right_capacity','EXO-49 Emancipator Exosuit / right_gun','weapon.capacity',100,150)
 scenario('patriot_hmg_capacity','EXO-45 Patriot Exosuit / right_gun','weapon.capacity',1350,2000)
 scenario('patriot_hmg_fire_rate','EXO-45 Patriot Exosuit / right_gun','weapon.fire_rate',1200,600)
 scenario('patriot_missile_damage','EXO-45 Patriot Exosuit / left_gun','damage.primary.standard_damage',1250,2000,
  {allow_shared=true})
 -- Independent arms: one arm's capacity changes, the other arm's record does not.
 reset()
 local left=weapons.validate_patch({id='left',target=hd2_target('EXO-49 Emancipator Exosuit / left_gun','weapon.capacity').target,
  field='weapon.capacity',expect=100,value=150})
 local plan=resolve(weapons,left);guarded.apply(runtime,plan)
 local right=weapons.validate_patch({id='right',target=hd2_target('EXO-49 Emancipator Exosuit / right_gun','weapon.capacity').target,
  field='weapon.capacity',expect=100,value=100})
 local other=resolve(weapons,right)
 assert(other.changes[1].owner.base+other.changes[1].offset~=plan.changes[1].owner.base+plan.changes[1].offset,
  'Emancipator arms share a magazine record')
 assert(guarded.apply(runtime,other).status=='ALREADY_DESIRED','right arm changed with the left')
 result.independentArms=true
 reset()

 -- Stratagem mission uses.
 local snames={};for name in pairs(strat_db.stratagems)do snames[#snames+1]=name end;table.sort(snames)
 local uses=result.stratagemUses
 for _,name in ipairs(snames)do
  for _,field in ipairs(strat_db.stratagems[name].fields)do
   if field.semanticFieldId=='stratagem.max_uses'and field.target.path=='stratagem'and field.editable then
    local target={resource='stratagem',stratagem=name,path='stratagem'}
    local current=field.currentDefault
    local value,transition
    if current=='unlimited'then value,transition=2,'unlimited_to_finite'
    elseif field.gameplayProvenValues[1]=='unlimited'then value,transition='unlimited','finite_to_unlimited'
    else value,transition=current+2,'finite_to_finite' end
    local proven=value=='unlimited'and field.gameplayProvenValues[1]=='unlimited'
    reset()
    local plan=resolve(stratagems,stratagems.validate_patch({id='uses',target=target,field=field.semanticFieldId,
     expect=current,value=current}))
    assert(guarded.apply(runtime,plan).status=='ALREADY_DESIRED',name..' uses no-op changed state')
    local spec=stratagems.validate_patch({id='uses',target=target,field=field.semanticFieldId,expect=current,value=value,
     allow_unverified_effect=not proven or nil})
    plan=round_trip(stratagems,spec,name..' uses')
    local part=plan.changes[1]
    assert(part.field_offset==80,name..' uses offset changed')
    assert(value~='unlimited'or part.desired=='\255\255\255\255',name..' unlimited is not the native value')
    assert(current~='unlimited'or part.before=='\255\255\255\255',name..' unlimited baseline is not native')
    poke(part.owner.base+part.offset,b.encode(77,'u32'))
    rejects(function()resolve(stratagems,spec)end,'CONFLICT',name..' uses conflict')
    uses.conflictRejections=uses.conflictRejections+1
    reset()
    if not proven then
     rejects(function()stratagems.validate_patch({id='uses',target=target,field=field.semanticFieldId,
      expect=current,value=value})end,'allow_unverified_effect',name..' uses without acknowledgement')
     uses.acknowledgementRejections=uses.acknowledgementRejections+1
    else uses.proven=uses.proven+1 end
    uses.checked=uses.checked+1
    uses.transitions[transition]=(uses.transitions[transition]or 0)+1
    -- A second, different transition on finite roots: finite -> different finite.
    if current~='unlimited'and value=='unlimited'then
     round_trip(stratagems,stratagems.validate_patch({id='uses2',target=target,field=field.semanticFieldId,
      expect=current,value=current+2,allow_unverified_effect=true}),name..' finite uses')
     uses.transitions.finite_to_finite=(uses.transitions.finite_to_finite or 0)+1
    end
    if name=='EXO-45 Patriot Exosuit'then
     result.scenarios.exosuit_unlimited_uses={stratagem=name,from=current,to='unlimited',before=b.hex(part.before),
      after=b.hex(part.desired),acknowledgement='not required (gameplay-proven)'}
    elseif name=='M-102 Gunner FRV'then
     result.scenarios.unlimited_to_finite_uses={stratagem=name,from='unlimited',to=2,before=b.hex(part.before),
      after=b.hex(part.desired),acknowledgement='allow_unverified_effect'}
    elseif name=='Orbital Laser'then
     result.scenarios.finite_to_finite_uses={stratagem=name,from=current,to=value,before=b.hex(part.before),
      after=b.hex(part.desired),acknowledgement='allow_unverified_effect'}
    end
   end
  end
 end
 end
 reset()
 source.close()
 return result
end)
local ok,out
repeat ok,out=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,out);return json.encode(out)
'''


def validate(snapshot, jobs=None):
    """Vehicle weapons are independent (every check starts from a reset overlay), so they are split across
    parallel Lua states; the one-off scenarios and stratagem uses run once, in their own state."""
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    head = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
        + lua(Path(snapshot).name) + '\nlocal hd2_target\n')
    return sharded_validation.run(head, PROGRAM, jobs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parallel.add_argument(parser)
    args = parser.parse_args()
    parallel.configure(args.jobs)
    result = validate(args.snapshot, args.jobs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', newline='\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
