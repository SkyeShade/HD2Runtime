"""Exercise every writable fire_mode.* field on a copy-on-write overlay of the retained snapshot.

For each player and support weapon whose fire-mode set is writable:

1. The reviewed mode set and burst rounds apply as guarded no-ops (ALREADY_DESIRED).
2. A changed set writes the four packed FireMode slots exactly (add the first missing mode where a
   selector is bound, otherwise replace the single mode), reads back, and rolls back; burst rounds
   likewise.
3. A third-party slot value is rejected as CONFLICT.
4. A missing allow_unverified_effect is rejected.
5. (0.31.0) Every 'addable' weapon (one mode, a free input: research/fire-mode-selector) gains a second mode together
   with its Firemode binding in one transaction (one slot and one input written, exact rollback); the modes alone and
   the binding alone are refused (SELECTOR_REQUIRED), and four modes are refused everywhere (the selector cycles
   three).

It also pins the JAR-5 Dominator full-auto write (only tertiary_fire_mode +152 changes, 0 -> 1),
checks that blocked weapons (charge, wind-up and special-trigger weapons) refuse writes, and that the
overlapping older fire-mode field cannot be combined with fire_mode.modes in one plan.
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

OUTPUT = ROOT / 'validation/fire-mode-authoring-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local domain=require('hd2runtime/domains/player_weapon_writes')
local players=require('hd2runtime/domains/player_weapon_authoring')
local supports=require('hd2runtime/domains/support_weapon_authoring')
local MODES,BURST='fire_mode.modes','fire_mode.burst_rounds'
local ORDER={'automatic','single','burst'}
local function resolve(spec)
 local reader=Reader.new(runtime)
 local resolved=domain.capture(runtime,reader,spec)
 local plan=domain.prepare(resolved,reader,spec);reader.verify()
 return plan
end
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
end
local function changed_modes(field)
 local current=field.currentDefault;local result={}
 for index,name in ipairs(current)do result[index]=name end
 if field.maxModes==1 or field.fireModeState=='addable'then
  result[1]=current[1]=='automatic'and'single'or'automatic';return result
 end
 local present={};for _,name in ipairs(current)do present[name]=true end
 for _,name in ipairs(ORDER)do if not present[name]then result[#result+1]=name;return result end end
 result[#result]=nil;return result   -- all three present: remove the last non-default mode
end
local function field_of(weapon,id)
 for _,item in ipairs(weapon.fields or{})do if item.semanticFieldId==id and item.editable then return item end end
end
local result={status='VALIDATED',weapons={},modeSetChecks=0,burstChecks=0,changedWrites=0,rollbacks=0,
 conflictRejections=0,acknowledgementRejections=0,blockedRejections=0,addedAutomatic=0,replacedSingleMode=0,
 removedModes=0,addedSelectors=0,selectorRejections=0,fourModeRejections=0,fixtureFallback='disabled',
 mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 for _,set in ipairs({{kind='player_weapon',db=players},{kind='support_weapon',db=supports}})do
  local names={};for name in pairs(set.db.weapons)do names[#names+1]=name end;table.sort(names)
  for _,name in ipairs(names)do
   local weapon=set.db.weapons[name]
   local modes=field_of(weapon,MODES)
   if modes and not weapon.ordinaryWritesBlocked then
    local target={resource=set.kind,path='weapon',weapon=name}
    local function request(field,expect,value,ack)
     return {id='fire-mode-check',target=target,field=field,expect=expect,value=value,allow_unverified_effect=ack}
    end
    for _,item in ipairs({{MODES,modes,changed_modes(modes)},{BURST,field_of(weapon,BURST)}})do
     local id,field,value=item[1],item[2],item[3]
     if id==BURST then
      value=field.currentDefault<field.max and field.currentDefault+1 or field.currentDefault-1
     end
     reset()
     local plan=resolve(domain.validate_patch(request(id,field.currentDefault,field.currentDefault,true)))
     local checked=guarded.apply(runtime,plan)
     assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,'fire-mode no-op changed state: '..name..' '..id)
     local spec=domain.validate_patch(request(id,field.currentDefault,value,true))
     plan=resolve(spec)
     local changed=0
     for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed=changed+1 end end
     local applied=guarded.apply(runtime,plan)
     assert(applied.status=='APPLIED'and applied.writes==changed and applied.non_target_bytes_unchanged,
      'fire-mode write failed: '..name..' '..id..' '..tostring(applied.reason))
     for _,part in ipairs(plan.changes)do
      assert(runtime.read(part.owner.base+part.offset,#part.desired)==part.desired,'write did not land: '..name)
     end
     local restored=guarded.apply(runtime,guarded.inverse(plan))
     assert(restored.status=='APPLIED','fire-mode rollback failed: '..name..' '..id)
     for _,part in ipairs(plan.changes)do
      assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,'fire-mode rollback failed: '..name)
     end
     local change=plan.changes[#plan.changes]
     result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
     poke(plan.changes[1].owner.base+plan.changes[1].offset,b.encode(5,'u32'))
     rejects(function()resolve(spec)end,'CONFLICT','conflict')
     result.conflictRejections=result.conflictRejections+1
     reset()
     rejects(function()domain.validate_patch(request(id,field.currentDefault,value,nil))end,
      'allow_unverified_effect','missing effect acknowledgement')
     result.acknowledgementRejections=result.acknowledgementRejections+1
     if id==MODES then
      result.modeSetChecks=result.modeSetChecks+1
      if field.maxModes==1 or field.fireModeState=='addable'then result.replacedSingleMode=result.replacedSingleMode+1
      elseif #value>#field.currentDefault then result.addedAutomatic=result.addedAutomatic+(value[#value]=='automatic'and 1 or 0)
      else result.removedModes=result.removedModes+1 end
      result.weapons[#result.weapons+1]={kind=set.kind,weapon=name,from=field.currentDefault,to=value}
     else result.burstChecks=result.burstChecks+1 end
    end
   end
  end
 end
 -- Addable weapons (0.31.0): a second mode with the Firemode binding, one transaction; neither alone.
 for _,set in ipairs({{kind='player_weapon',db=players},{kind='support_weapon',db=supports}})do
  local names={};for name in pairs(set.db.weapons)do names[#names+1]=name end;table.sort(names)
  for _,name in ipairs(names)do
   local weapon=set.db.weapons[name]
   local modes=field_of(weapon,MODES)
   if modes and not weapon.ordinaryWritesBlocked and modes.fireModeState=='addable'then
    local target={resource=set.kind,path='weapon',weapon=name}
    local input='weapon_function.'..modes.bindableInputs[1]
    local current=modes.currentDefault
    local two={current[1],current[1]=='automatic'and'single'or'automatic'}
    reset()
    local plan=resolve(domain.validate_transaction({id='fire-selector',target=target,allow_unverified_effect=true,
     changes={{field=MODES,expect=current,value=two},{field=input,expect='none',value='fire_mode'}}}))
    local changed={}
    for _,part in ipairs(plan.changes)do if part.before~=part.desired then changed[#changed+1]=part end end
    assert(#changed==2,name..' selector plans '..#changed..' changed slots')
    local applied=guarded.apply(runtime,plan)
    assert(applied.status=='APPLIED'and applied.writes==2 and applied.non_target_bytes_unchanged,
     'selector write failed: '..name..' '..tostring(applied.reason))
    local slot,binding
    for _,part in ipairs(changed)do
     if part.field_offset==148 then slot=part elseif part.field_offset==184 or part.field_offset==188 then binding=part end
    end
    assert(slot and binding and b.u32(binding.desired,0)==3,name..': the second slot and the Firemode binding')
    local restored=guarded.apply(runtime,guarded.inverse(plan))
    assert(restored.status=='APPLIED','selector rollback failed: '..name)
    for _,part in ipairs(plan.changes)do
     assert(runtime.read(part.owner.base+part.offset,#part.before)==part.before,'selector rollback failed: '..name)
    end
    result.addedSelectors=result.addedSelectors+1
    if name=='R/40-K Hot-Shot Marksman Rifle'then
     result.hotShot={modes=two,secondSlot={offset=148,before=b.hex(slot.before),after=b.hex(slot.desired)},
      binding={field=input,offset=binding.field_offset,before=b.hex(binding.before),after=b.hex(binding.desired)},
      writes=applied.writes}
    end
    rejects(function()domain.validate_patch({id='m',target=target,field=MODES,expect=current,value=two,
     allow_unverified_effect=true})end,'SELECTOR_REQUIRED','modes without the binding')
    rejects(function()domain.validate_patch({id='i',target=target,field=input,expect='none',value='fire_mode',
     allow_unverified_effect=true})end,'SELECTOR_REQUIRED','the binding without modes')
    result.selectorRejections=result.selectorRejections+2
    rejects(function()domain.validate_transaction({id='f',target=target,allow_unverified_effect=true,changes={
     {field=MODES,expect=current,value={'single','automatic','burst','single'}},
     {field=input,expect='none',value='fire_mode'}}})end,'allows 3','four modes')
    result.fourModeRejections=result.fourModeRejections+1
   end
  end
 end
 reset()
 -- JAR-5 Dominator: full-auto is the Automatic value in the empty tertiary slot; nothing else changes.
 reset()
 local jar={resource='player_weapon',path='weapon',weapon='JAR-5 Dominator'}
 local plan=resolve(domain.validate_patch({id='jar5-full-auto',target=jar,field=MODES,expect={'single','burst'},
  value={'single','burst','automatic'},allow_unverified_effect=true}))
 assert(#plan.changes==4,'JAR-5 mode set is not four slots')
 local before,after,written={},{},{}
 for index,part in ipairs(plan.changes)do
  assert(part.field_offset==140+4*index,'JAR-5 slot offsets changed')
  before[index]=b.hex(part.before);after[index]=b.hex(part.desired)
  if part.before~=part.desired then written[#written+1]=part end
 end
 assert(table.concat(before)=='02000000'..'03000000'..'00000000'..'00000000','JAR-5 baseline is not Single, Burst')
 assert(table.concat(after)=='02000000'..'03000000'..'01000000'..'00000000','JAR-5 full-auto bytes differ')
 assert(#written==1 and written[1].field_offset==152,'JAR-5 full-auto must write only tertiary_fire_mode')
 local applied=guarded.apply(runtime,plan)
 assert(applied.status=='APPLIED'and applied.writes==1 and applied.bytes_written==4 and applied.non_target_bytes_unchanged,
  'JAR-5 full-auto write failed')
 local change=written[1]
 result.jar5={owner='WeaponDataComponentData',record=change.identity.record_index,fieldOffset=152,
  changedSlot='tertiary_fire_mode (+152)',before=b.hex(change.before),after=b.hex(change.desired),
  bytesWritten=applied.bytes_written,uniqueOwner=change.identity.unique_owner}
 reset()
 -- Blocked weapons never accept fire-mode writes.
 for _,item in ipairs({{'player_weapon','PLAS-15 Loyalist'},{'support_weapon','RS-422 Railgun'},
   {'support_weapon','M-1000 Maxigun'},{'player_weapon','P-92 Warrant'},{'support_weapon','GR-8 Recoilless Rifle'}})do
  local ok=pcall(domain.validate_patch,{id='blocked',target={resource=item[1],path='weapon',weapon=item[2]},
   field=MODES,expect={'single'},value={'automatic'},allow_unverified_effect=true})
  assert(not ok,item[2]..' accepted a fire-mode write')
  result.blockedRejections=result.blockedRejections+1
 end
 -- The older fire-mode view overlaps the same bytes and is never combined with the mode set.
 rejects(function()resolve(domain.validate_transaction({id='overlap',target={resource='player_weapon',path='weapon',
   weapon='AR-23 Liberator'},allow_unverified_effect=true,changes={
   {field=MODES,expect={'automatic','single','burst'},value={'automatic','single'}},
   {field='weapon.default_fire_mode',expect=1,value=2}}}))end,'overlapping semantic fields','overlapping fire-mode views')
 result.overlapRejected=true
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
    print(json.dumps({k: v for k, v in result.items() if k != 'weapons'}, indent=2))


if __name__ == '__main__':
    main()
