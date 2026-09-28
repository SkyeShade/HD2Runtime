"""Resolve every writable stratagem object against the retained snapshot without writing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)
SNAPSHOT = build_profile.SNAPSHOT
OUTPUT=ROOT/'validation/stratagem-authoring-snapshot.json'

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
local domain=require('hd2runtime/domains/stratagem_writes')
local database=require('hd2runtime/domains/stratagem_authoring')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local specs={};local seen_rearm=false
 local names={};for name in pairs(database.stratagems)do names[#names+1]=name end;table.sort(names)
 for _,name in ipairs(names)do
  local entry=database.stratagems[name]
  local grouped={}
  for _,field in ipairs(entry.fields)do if field.editable then
   local target=field.target
   if target.path~='eagle_rearm'or not seen_rearm then
    local key=target.path..':'..tostring(target.attack)..':'..tostring(target.zone)..':'..field.operationGroup
    local group=grouped[key]or{target={resource='stratagem',stratagem=name,path=target.path,
     entity=target.entity,weapon=target.weapon,attack=target.attack,zone=target.zone},
     allow_shared=field.shared,changes={}}
    group.allow_shared=group.allow_shared or field.shared
    group.changes[#group.changes+1]={field=field.semanticFieldId,
     expect=field.currentDefault,value=field.currentDefault}
    grouped[key]=group
    if target.path=='eagle_rearm'then seen_rearm=true end
   end
  end end
  local index=0;for _,request in pairs(grouped)do index=index+1
   request.id='snapshot_'..#specs+1
   specs[#specs+1]=domain.validate_transaction(request)
  end
 end
 local reader=Reader.new(source)
 local resolved=domain.capture_many(source,reader,specs)
 local fields,changes=0,0
 for index,spec in ipairs(specs)do
  local plan=domain.prepare(resolved[index],reader,spec)
  fields=fields+#spec.changes;changes=changes+#plan.changes
 end
 reader.verify();source.close()
 return {status='VALIDATED',objects=#specs,fieldInstances=fields,physicalChanges=changes,
  researchWrites=0,protectionChanges=0,fixtureFallback='disabled',mode='snapshot',
  snapshot='''+lua(build_profile.SNAPSHOT_NAME)+r'''}
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
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
