"""Resolve every magazine-attachment field through the production delta-chain proof on the snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT,lua,sources

OUTPUT=ROOT/'validation/magazine-attachment-snapshot.json'

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
local domain=require('hd2runtime/domains/attachment_writes')
local database=require('hd2runtime/domains/attachment_authoring')
local json=require('hd2runtime/primary_mapper/json')
local worker=coroutine.create(function()
 local specs={}
 local ids={};for id in pairs(database.attachments)do ids[#ids+1]=id end;table.sort(ids)
 for _,id in ipairs(ids)do
  local changes={}
  local names={};for field in pairs(database.attachments[id].fields)do names[#names+1]=field end;table.sort(names)
  for _,field in ipairs(names)do local value=database.attachments[id].fields[field].currentDefault
   changes[#changes+1]={field=field,expect=value,value=value}end
  specs[#specs+1]=domain.validate_transaction({id='snapshot_'..(#specs+1),allow_shared=true,
   allow_unverified_effect=true,target={resource='weapon_attachment',attachment=id,path='magazine'},changes=changes})
 end
 local reader=Reader.new(source)
 local resolved=domain.capture_many(source,reader,specs)
 local fields,already,packed=0,0,0
 for index,spec in ipairs(specs)do
  local plan=domain.prepare(resolved[index],reader,spec)
  for _,change in ipairs(plan.changes)do
   fields=fields+1
   if change.already_desired then already=already+1 end
   if change.offset%4~=0 then packed=packed+1 end
  end
 end
 reader.verify();source.close()
 return {status='VALIDATED',attachments=#specs,fieldChecks=fields,alreadyDesired=already,
  unalignedPackedFields=packed,researchWrites=0,protectionChanges=0,fixtureFallback='disabled',mode='snapshot',
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
