"""Exercise every muzzle, optics and underbarrel stat-modifier field through the production delta-chain proof.

For every reviewed field on a copy-on-write memory overlay of the retained snapshot (no game process):

1. The current value applies as a guarded no-op (ALREADY_DESIRED, zero writes).
2. A changed in-range value applies through the guarded transaction core, reads back at the delta data
   offset, leaves every other reviewed attachment byte (all four slots, magazines included) untouched, and its
   guarded inverse restores it.
3. A third-party value at the target is rejected as CONFLICT.
4. A changed modifier type word is rejected by the live guard (each pair is guarded by its own type word).
5. Missing acknowledgements, out-of-range values and a target path of another slot are rejected before any
   memory access.

For every definition it also checks that a stat modifier the definition does not carry is refused (pairs are
never added), and it applies one transaction that edits every modifier of the 5,5mm. Flash Hider at once and rolls
it back. Output: validation/weapon-attachment-modifier-snapshot.json.
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

OUTPUT = ROOT / 'validation/weapon-attachment-modifier-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY + r'''
local region
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 region=resolved.region
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan
end
local function request(id,field,expect,value,extra)
 local r={id='attachment-modifier-check',allow_shared=true,allow_unverified_effect=true,
  target={resource='weapon_attachment',attachment=id,path=database.attachments[id].slot},field=field,expect=expect,
  value=value}
 for k,v in pairs(extra or{})do if v==false then r[k]=nil else r[k]=v end end
 return r
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function changed(field)
 local candidate=field.currentDefault+0.5
 if field.max and candidate>field.max then candidate=field.currentDefault-0.5 end
 return candidate
end
local OTHER={muzzle='optics',optics='underbarrel',underbarrel='muzzle'}
-- Every schema stat-modifier field, to prove an absent modifier is refused rather than added.
local MODIFIER_FIELDS={'attachment.ergonomics_modifier','attachment.modifier.sway','attachment.modifier.recoil_horizontal',
 'attachment.modifier.recoil_vertical','attachment.modifier.climb_horizontal','attachment.modifier.climb_vertical',
 'attachment.modifier.spread_horizontal','attachment.modifier.spread_vertical'}

local all_ids={};for id in pairs(database.attachments)do all_ids[#all_ids+1]=id end;table.sort(all_ids)
local locations,targets={},{}
for _,id in ipairs(all_ids)do
 local entry=database.attachments[id]
 local names={};for name in pairs(entry.fields)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local location={id=id,field=name,descriptor=entry.fields[name],slot=entry.slot}
  locations[#locations+1]=location
  if entry.slot~='magazine'then targets[#targets+1]=location end
 end
end

local result={status='VALIDATED',attachments=0,attachmentsWithFields=0,fieldChecks=0,alreadyDesired=0,changedWrites=0,
 rollbacks=0,isolationChecks=0,isolatedLocations=#locations,conflictRejections=0,guardRejections=0,
 acknowledgementRejections=0,rangeRejections=0,slotRejections=0,absentModifierRejections=0,blockedModifierRejections=0,
 unalignedPackedFields=0,
 byField={},bySlot={},fixtureFallback='disabled',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 reset()
 resolve(domain.validate_patch(request(targets[1].id,targets[1].field,
  targets[1].descriptor.currentDefault,targets[1].descriptor.currentDefault)))
 local baseline={}
 for index,location in ipairs(locations)do baseline[index]=source.read(region.base+location.descriptor.dataOffset,4)end
 for _,location in ipairs(targets)do
  local id,name,field=location.id,location.field,location.descriptor
  assert(field.guard,'stat modifier field without a type guard: '..field.instanceKey)
  reset()
  -- 1. guarded no-op
  local plan=resolve(domain.validate_patch(request(id,name,field.currentDefault,field.currentDefault)))
  local checked=guarded.apply(runtime,plan)
  assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0,
   'attachment no-op changed state: '..field.instanceKey)
  result.fieldChecks=result.fieldChecks+1
  result.byField[name]=(result.byField[name]or 0)+1
  result.bySlot[location.slot]=(result.bySlot[location.slot]or 0)+1
  if plan.changes[1].already_desired then result.alreadyDesired=result.alreadyDesired+1 end
  if plan.changes[1].offset%4~=0 then result.unalignedPackedFields=result.unalignedPackedFields+1 end
  -- 2. changed value, read-back, isolation, guarded inverse
  local value=changed(field)
  local spec=domain.validate_patch(request(id,name,field.currentDefault,value))
  plan=resolve(spec)
  local change=plan.changes[1]
  local applied=guarded.apply(runtime,plan)
  assert(applied.status=='APPLIED'and applied.writes==1 and applied.protection_restored
   and applied.non_target_bytes_unchanged,'attachment write failed: '..field.instanceKey..' '..tostring(applied.reason))
  assert(runtime.read(region.base+field.dataOffset,4)==change.desired,'attachment write did not land: '..field.instanceKey)
  assert(math.abs(b.value(runtime.read(region.base+field.dataOffset,4),0,'f32')-value)<0.0001,
   'attachment write reads back another value: '..field.instanceKey)
  for index,other in ipairs(locations)do
   if other~=location then
    assert(runtime.read(region.base+other.descriptor.dataOffset,4)==baseline[index],
     'writing '..field.instanceKey..' changed '..other.descriptor.instanceKey)
   end
  end
  result.isolationChecks=result.isolationChecks+1
  local again=resolve(domain.validate_patch(request(id,name,field.currentDefault,value)))
  assert(again.changes[1].already_desired,'changed value is not recognised as desired: '..field.instanceKey)
  local restored=guarded.apply(runtime,guarded.inverse(plan))
  assert(restored.status=='APPLIED'and runtime.read(region.base+field.dataOffset,4)==change.before,
   'attachment rollback failed: '..field.instanceKey)
  for page in pairs(protection)do error('page protection not restored for '..field.instanceKey)end
  result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
  -- 3. third-party value
  poke(region.base+field.dataOffset,b.encode(field.currentDefault+7.25,'f32'))
  rejects(function()resolve(spec)end,'CONFLICT','conflict')
  result.conflictRejections=result.conflictRejections+1
  -- 4. stat modifier type guard: another modifier type in this pair's type word
  reset()
  poke(region.base+field.guard.dataOffset,b.encode((field.guard.u32+1)%18,'u32'))
  rejects(function()resolve(spec)end,'no longer '..database.modifierTypes[tostring(field.guard.u32)],'changed modifier type')
  result.guardRejections=result.guardRejections+1
  reset()
  -- 5. acknowledgements, range and slot, before any memory access
  rejects(function()domain.validate_patch(request(id,name,field.currentDefault,value,{allow_unverified_effect=false}))end,
   'allow_unverified_effect','missing effect acknowledgement')
  rejects(function()domain.validate_patch(request(id,name,field.currentDefault,value,{allow_shared=false}))end,
   'allow_shared','missing shared acknowledgement')
  result.acknowledgementRejections=result.acknowledgementRejections+2
  rejects(function()domain.validate_patch(request(id,name,field.currentDefault,field.max+1))end,'maximum','range')
  rejects(function()domain.validate_patch(request(id,name,field.currentDefault,field.min-1))end,'minimum','range')
  result.rangeRejections=result.rangeRejections+2
  local wrong=request(id,name,field.currentDefault,value)
  wrong.target.path=OTHER[location.slot]
  rejects(function()domain.validate_patch(wrong)end,'attachment, not '..OTHER[location.slot],'other slot path')
  wrong.target.path='magazine'
  rejects(function()domain.validate_patch(wrong)end,'attachment, not magazine','magazine path')
  result.slotRejections=result.slotRejections+2
 end
 -- Every definition: a modifier it does not carry is refused, never added.
 for _,id in ipairs(all_ids)do
  local entry=database.attachments[id]
  if entry.slot~='magazine'then
   result.attachments=result.attachments+1
   if next(entry.fields)then result.attachmentsWithFields=result.attachmentsWithFields+1 end
   local blocked={}
   for _,m in ipairs(entry.modifiers)do if not m.writable and m.field then blocked[m.field]=m.blocker end end
   for _,name in ipairs(MODIFIER_FIELDS)do
    if blocked[name]then
     -- Carried but not writable (its reviewed blocker, e.g. a value straddling a page of the live allocation).
     rejects(function()domain.validate_patch(request(id,name,1,1))end,blocked[name],'blocked modifier '..name)
     result.blockedModifierRejections=result.blockedModifierRejections+1
    elseif not entry.fields[name]then
     rejects(function()domain.validate_patch(request(id,name,1,1))end,'adding a modifier is not supported',
      'absent modifier '..name)
     result.absentModifierRejections=result.absentModifierRejections+1
    end
   end
  end
 end
 -- One definition, every modifier in one transaction, then the guarded inverse.
 local flash=assert(database.names['5,5mm. Flash Hider'])
 local entry=database.attachments[flash]
 local changes,names={},{}
 for name in pairs(entry.fields)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local field=entry.fields[name]
  changes[#changes+1]={field=name,expect=field.currentDefault,value=changed(field)}
 end
 reset()
 local spec=domain.validate_transaction({id='flash-hider-all',allow_shared=true,allow_unverified_effect=true,
  target={resource='weapon_attachment',attachment=flash,path='muzzle'},changes=changes})
 local plan=resolve(spec)
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==#changes,'flash hider transaction failed: '..tostring(applied.reason))
 for _,item in ipairs(changes)do
  assert(math.abs(b.value(runtime.read(region.base+entry.fields[item.field].dataOffset,4),0,'f32')-item.value)<0.0001,
   'flash hider transaction did not land: '..item.field)
 end
 local restored=guarded.apply(runtime,guarded.inverse(plan))
 assert(restored.status=='APPLIED','flash hider rollback failed')
 for index,location in ipairs(locations)do
  assert(runtime.read(region.base+location.descriptor.dataOffset,4)==baseline[index],'flash hider rollback left '
   ..location.descriptor.instanceKey)
 end
 result.transaction={attachment='5,5mm. Flash Hider',slot='muzzle',changes=#changes,applied=true,rolledBack=true}
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
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
