"""Resolve every promoted support field against the retained read-only snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'))
from tools.lua_runner import execute
from generate_support_weapon_authoring import build,lua

DEFAULT_SNAPSHOT=Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
DEFAULT_OUTPUT=ROOT/'research/support-weapon-authoring-validation-F5FEE03DCFDB.json'


def module_sources():
    result={}
    for folder in ('api','core','runtime','schemas','domains','primary_mapper'):
        for path in sorted((ROOT/folder).glob('*.lua')):
            result['hd2runtime/'+path.relative_to(ROOT).with_suffix('').as_posix()]=path.read_text()
    return result


def public_field(field):
    field_id=field['semanticFieldId'];target=field['target'];role=target.get('attack')
    if target['path']=='weapon':return field_id
    if field_id.startswith('explosion.'+str(role)+'.'):
        return 'explosion.'+field_id[len('explosion.'+str(role)+'.'):]
    for domain in ('projectile','damage','arc','beam','status'):
        prefix=domain+'.'+str(role)+'.'
        if field_id.startswith(prefix):return domain+'.'+field_id[len(prefix):]
    raise ValueError('Cannot publicize support field '+field_id)


def validate(snapshot=DEFAULT_SNAPSHOT,output=DEFAULT_OUTPUT):
    snapshot=Path(snapshot).resolve();output=Path(output)
    if not snapshot.is_file():raise ValueError('Snapshot file not found: '+str(snapshot))
    runtime,_=build();audit=[]
    for weapon in runtime['weapons'].values():
        if weapon['ordinaryWritesBlocked']:
            audit.append({'name':weapon['name'],'blocked':True,'batches':[]});continue
        grouped={}
        for field in weapon['fields']:
            target=field['target'];key=json.dumps(target,sort_keys=True)
            grouped.setdefault(key,{'target':target,'changes':[]})['changes'].append({
                'field':public_field(field),'expect':field['currentDefault'],
                'value':field['currentDefault']})
        audit.append({'name':weapon['name'],'blocked':False,'batches':list(grouped.values())})
    sources=module_sources()
    preload='\n'.join('package.preload['+lua(name)+']=function(...) return assert(loadstring('
        +lua(body)+','+lua(name)+'))(...) end'for name,body in sources.items())
    program=preload+r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open('''+lua(str(snapshot))+r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local domain=require('hd2runtime/domains/player_weapon_writes')
local guarded=require('hd2runtime/core/guarded_transaction')
local audit='''+lua(audit)+r'''
local result={weapons=0,fields=0,projectileBranches=0,explosionBranches=0,blocked=0,
 failures={},writes=0,protectionChanges=0,fixtureFallback='disabled',mode='snapshot'}
for _,weapon in ipairs(audit)do
 if weapon.blocked then
  result.blocked=result.blocked+1
  local ok=pcall(domain.validate_patch,{id='duplicate-block',
   target={resource='support_weapon',path='weapon',weapon=weapon.name},
   field='weapon.fire_rate',expect=1,value=1})
  assert(not ok,'duplicate support identity unexpectedly writable')
 else
  result.weapons=result.weapons+1
  for _,batch in ipairs(weapon.batches)do
   local worker=coroutine.create(function()
    local spec=domain.validate_transaction{id='support-snapshot-audit',allow_shared=true,
     allow_unverified_effect=true,
     target=batch.target,changes=batch.changes}
    local reader=Reader.new(source);local resolved=domain.capture(source,reader,spec)
    local plan=domain.prepare(resolved,reader,spec);reader.verify()
    assert(#plan.changes==#batch.changes,'physical support field count changed')
    local checked=guarded.apply(source,plan)
    assert(checked.status=='ALREADY_DESIRED'and checked.writes==0
     and checked.protection_changes==0 and checked.protection_restored)
    return #batch.changes
   end)
   local ok,value
   repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
   if not ok then result.failures[#result.failures+1]={weapon=weapon.name,
    path=batch.target.path,attack=batch.target.attack,error=tostring(value)}
   else
    result.fields=result.fields+value
    if batch.target.path=='projectile_reference'then
     result.projectileBranches=result.projectileBranches+1
    elseif batch.target.path=='explosion'then
     result.explosionBranches=result.explosionBranches+1
    end
   end
  end
 end
end
source.close()
return require('hd2runtime/primary_mapper/json').encode(result)
'''
    result=json.loads(execute(program.encode()))
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path,nargs='?',default=DEFAULT_SNAPSHOT)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args();result=validate(args.snapshot,args.output);print(json.dumps(result,indent=2))
    if result['failures']:raise SystemExit(1)
