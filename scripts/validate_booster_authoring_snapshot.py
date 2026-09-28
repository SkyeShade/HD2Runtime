"""Resolve every Booster field through the production chain proofs on the retained snapshot.

Each reviewed target is validated with its current values, resolved (including the live
stratagem booster entry, entity delta, and status row checks), prepared, and applied through
the guarded transaction core. The result must be ALREADY_DESIRED with zero writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources

OUTPUT = ROOT / 'validation/booster-authoring-snapshot.json'


def validate(snapshot):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + lua(Path(snapshot).resolve()) + r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local domain=require('hd2runtime/domains/booster_writes')
local database=require('hd2runtime/domains/booster_authoring')
local guarded=require('hd2runtime/core/guarded_transaction')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local result={status='VALIDATED',boosters=0,targets=0,fieldChecks=0,alreadyDesired=0,writes=0,
  protectionChanges=0,fixtureFallback='disabled',mode='snapshot',
  snapshot='F5FEE03DCFDB-20260926T222226Z.hd2snap'}
 local names={};for name in pairs(database.boosters)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local entry=database.boosters[name];local any=false
  local paths={};for path in pairs(entry.targets)do paths[#paths+1]=path end;table.sort(paths)
  for _,path in ipairs(paths)do
   local groups={}
   for field_id,field in pairs(entry.targets[path].fields)do
    groups[field.operationGroup]=groups[field.operationGroup]or{}
    table.insert(groups[field.operationGroup],{field=field_id,expect=field.currentDefault,value=field.currentDefault})
   end
   for _,changes in pairs(groups)do
    table.sort(changes,function(a,b)return a.field<b.field end)
    local spec=domain.validate_transaction{id='booster-snapshot',allow_shared=true,allow_unverified_effect=true,
     target={resource='booster',booster=name,path=path},changes=changes}
    local reader=Reader.new(source)
    local resolved=domain.capture(source,reader,spec)
    local plan=domain.prepare(resolved,reader,spec);reader.verify()
    local checked=guarded.apply(source,plan)
    assert(checked.status=='ALREADY_DESIRED'and checked.writes==0 and checked.protection_changes==0
     and checked.protection_restored,'booster no-op changed state: '..name..' '..path)
    for _,change in ipairs(plan.changes)do
     result.fieldChecks=result.fieldChecks+1
     if change.already_desired then result.alreadyDesired=result.alreadyDesired+1 end
    end
    result.targets=result.targets+1;any=true
   end
  end
  if any then result.boosters=result.boosters+1 end
 end
 source.close()
 return result
end)
local ok,result
repeat ok,result=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,result);return json.encode(result)
'''
    return json.loads(execute(program.encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
