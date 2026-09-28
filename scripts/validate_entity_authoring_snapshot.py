"""Resolve every writable vehicle/backpack object and mount candidate against the retained snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
OUTPUT=ROOT/'validation/entity-authoring-snapshot.json'

def lua(value): return json.dumps(str(value),ensure_ascii=False)

def sources():
    result={}
    for folder in ('api','core','runtime','schemas','domains','primary_mapper'):
        for path in sorted((ROOT/folder).glob('*.lua')):
            result['hd2runtime/'+path.relative_to(ROOT).with_suffix('').as_posix()]=path.read_text()
    return result

def validate(snapshot):
    sys.path.insert(0,str(ROOT/'sdk'))
    from tools.lua_runner import execute
    preload='\n'.join('package.preload['+lua(name)+']=function(...) return assert(loadstring('
        +lua(body)+','+lua(name)+'))(...) end' for name,body in sources().items())
    program=preload+r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open('''+lua(Path(snapshot).resolve())+r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local domain=require('hd2runtime/domains/entity_writes')
local database=require('hd2runtime/domains/entity_authoring')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local specs={};local candidates=0
 local function add(request)request.id='snapshot_'..(#specs+1);specs[#specs+1]=domain.validate_transaction(request)end
 for _,family in ipairs({'vehicle','backpack'})do
  local entries=family=='vehicle'and database.vehicles or database.backpacks
  local names={};for name in pairs(entries)do names[#names+1]=name end;table.sort(names)
  for _,name in ipairs(names)do
   local grouped={};local order={}
   for _,field in ipairs(entries[name].fields)do if field.editable then
    local target={resource=family,path=field.target.path,zone=field.target.zone,mount=field.target.mount}
    target[family]=name
    if field.type=='mounted_weapon_reference'then
     -- No-op on the current reference, then prove every allowed replacement is live.
     add({target=target,allow_shared=field.shared,allow_unverified_reference=true,
      changes={{field=field.semanticFieldId,expect=field.currentDefault,value=field.currentDefault}}})
     for _,candidate in ipairs(field.allowedValues)do
      candidates=candidates+1
      add({target=target,allow_shared=field.shared,allow_unverified_reference=true,
       changes={{field=field.semanticFieldId,expect=field.currentDefault,value=candidate}}})
     end
    else
     local key=field.operationGroup
     if not grouped[key]then grouped[key]={target=target,allow_shared=field.shared,changes={}};order[#order+1]=key end
     local changes=grouped[key].changes
     changes[#changes+1]={field=field.semanticFieldId,expect=field.currentDefault,value=field.currentDefault}
    end
   end end
   for _,key in ipairs(order)do add(grouped[key])end
  end
 end
 local reader=Reader.new(source)
 local resolved=domain.capture_many(source,reader,specs)
 local fields,changes,already,expected=0,0,0,0
 for index,spec in ipairs(specs)do
  local plan=domain.prepare(resolved[index],reader,spec)
  fields=fields+#spec.changes;changes=changes+#plan.changes
  for _,change in ipairs(plan.changes)do
   if change.already_desired then already=already+1 else expected=expected+1 end
  end
 end
 reader.verify();source.close()
 return {status='VALIDATED',operations=#specs,fieldChecks=fields,physicalChanges=changes,
  alreadyDesired=already,mountCandidatesResolvedLive=candidates,candidateSwapsAtExpectedState=expected,
  researchWrites=0,protectionChanges=0,fixtureFallback='disabled',mode='snapshot',
  snapshot='F5FEE03DCFDB-20260926T222226Z.hd2snap'}
end)
local ok,result
repeat ok,result=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,result);return json.encode(result)
'''
    return json.loads(execute(program.encode()))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,default=SNAPSHOT)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args();result=validate(args.snapshot)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
