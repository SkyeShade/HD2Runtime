"""Exercise every writable weapon.third_person_reticle field on a copy-on-write snapshot overlay.

For each player and support weapon whose crosshair policy is mapped:

1. The reviewed state applies as a guarded no-op (ALREADY_DESIRED).
2. The opposite state writes exactly the reviewed enum bytes (hidden = CrosshairDamageIndicatorOnly,
   shown = the weapon's own style, or AssaultRifle where the baseline is hidden), reads back, and its
   guarded inverse restores the original bytes.
3. A third-party crosshair value is rejected as CONFLICT.
4. A missing allow_unverified_effect is rejected wherever the change is not gameplay-proven.
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

OUTPUT = ROOT / 'validation/reticle-authoring-snapshot.json'
OVERLAY = overlay_source.PROGRAM[:overlay_source.PROGRAM.index('local region')]

PROGRAM = OVERLAY.replace("local domain=require('hd2runtime/domains/attachment_writes')\n", '').replace(
    "local database=require('hd2runtime/domains/attachment_authoring')\n", '') + r'''
local domain=require('hd2runtime/domains/player_weapon_writes')
local players=require('hd2runtime/domains/player_weapon_authoring')
local supports=require('hd2runtime/domains/support_weapon_authoring')
local FIELD='weapon.third_person_reticle'
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
local result={status='VALIDATED',weapons={},fieldChecks=0,changedWrites=0,rollbacks=0,conflictRejections=0,
 acknowledgementRejections=0,gameplayProven=0,fixtureFallback='disabled',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME}
local worker=coroutine.create(function()
 for _,set in ipairs({{kind='player_weapon',db=players},{kind='support_weapon',db=supports}})do
  local names={};for name in pairs(set.db.weapons)do names[#names+1]=name end;table.sort(names)
  for _,name in ipairs(names)do
   local weapon=set.db.weapons[name];local field
   for _,item in ipairs(weapon.fields or{})do if item.semanticFieldId==FIELD and item.editable then field=item end end
   if field and not weapon.ordinaryWritesBlocked then
    reset()
    local function request(expect,value,ack)
     return {id='reticle-check',target={resource=set.kind,path='weapon',weapon=name},field=FIELD,
      expect=expect,value=value,allow_unverified_effect=ack}
    end
    local ack=field.acknowledgement=='allow_unverified_effect'or nil
    local plan=resolve(domain.validate_patch(request(field.currentDefault,field.currentDefault,ack)))
    local checked=guarded.apply(runtime,plan)
    assert(checked.status=='ALREADY_DESIRED'and checked.writes==0,'reticle no-op changed state: '..name)
    result.fieldChecks=result.fieldChecks+1
    local spec=domain.validate_patch(request(field.currentDefault,not field.currentDefault,ack))
    plan=resolve(spec)
    local change=plan.changes[1]
    local target=field.encoding[(not field.currentDefault)and'on'or'off']
    assert(b.u32(change.desired,0)==target and b.u32(change.before,0)==field.nativeValue,'reticle encoding: '..name)
    local applied=guarded.apply(runtime,plan)
    assert(applied.status=='APPLIED'and applied.writes==1 and applied.non_target_bytes_unchanged,
     'reticle write failed: '..name..' '..tostring(applied.reason))
    assert(runtime.read(change.owner.base+change.offset,4)==change.desired,'reticle write did not land: '..name)
    local restored=guarded.apply(runtime,guarded.inverse(plan))
    assert(restored.status=='APPLIED'and runtime.read(change.owner.base+change.offset,4)==change.before,
     'reticle rollback failed: '..name)
    result.changedWrites=result.changedWrites+1;result.rollbacks=result.rollbacks+1
    poke(change.owner.base+change.offset,b.encode(1,'u32'))
    rejects(function()resolve(spec)end,'CONFLICT','conflict')
    result.conflictRejections=result.conflictRejections+1
    reset()
    if ack then
     rejects(function()domain.validate_patch(request(field.currentDefault,not field.currentDefault,nil))end,
      'allow_unverified_effect','missing effect acknowledgement')
     result.acknowledgementRejections=result.acknowledgementRejections+1
    else result.gameplayProven=result.gameplayProven+1 end
    result.weapons[#result.weapons+1]={kind=set.kind,weapon=name,baseline=field.currentDefault,
     from=field.nativeValue,to=target,acknowledgement=field.acknowledgement or'none'}
   end
  end
 end
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
