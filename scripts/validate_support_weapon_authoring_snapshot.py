"""Resolve every promoted support field against the retained read-only snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'))
from tools.lua_runner import execute
from generate_support_weapon_authoring import build,lua

DEFAULT_SNAPSHOT=build_profile.SNAPSHOT
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
    if field_id=='attack.'+str(role)+'.projectile':return 'attack.projectile'
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
        batches=[]
        for field in weapon['fields']:
            if not field['acceptedForWrites']:continue
            target=field['target'];backing=field['backing']
            expect=field['currentDefault']
            if field['type']=='function_projectile_reference':
                # The ProgrammableAmmo projectile: "none", or the weapon's own native one (restore handle).
                expect=({'resource':'support_weapon','path':'function_projectile','weapon':weapon['name']}
                    if expect['projectileType'] else 'none')
            if field['type']=='projectile_reference':
                # A support host's projectile reference: its own attack projectile (the reviewed baseline).
                expect={'resource':'support_weapon','path':'projectile_reference','weapon':weapon['name'],
                    'attack':target['attack']}
            if field['type']=='beam_reference':
                # A beam host's BeamType reference (0.30.4 beam swaps): its own beam (the reviewed baseline).
                expect={'resource':'support_weapon','path':'beam_reference','weapon':weapon['name']}
            # Differently sized views of the same bytes (fire_rate.modes and weapon.fire_rate, the two presentation
            # fields) are never combined in one plan: overlapping byte ranges of one record go to separate batches.
            owner=(backing['kind'],backing.get('component'),backing.get('settings'),backing.get('recordIndex'),
                backing.get('group'),backing.get('row'))
            span=(owner,backing['offset'],backing['offset']+backing['width'])
            change={'field':public_field(field),'expect':expect,'value':expect}
            for batch in batches:
                if batch['target']==target and len(batch['changes'])<32 and not any(other[0]==owner
                        and other[1]<span[2] and span[1]<other[2] for other in batch['spans']):
                    batch['changes'].append(change);batch['spans'].append(span);break
            else:
                batches.append({'target':target,'changes':[change],'spans':[span]})
        audit.append({'name':weapon['name'],'blocked':False,
            'batches':[{'target':batch['target'],'changes':batch['changes']} for batch in batches]})
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
    -- Native slot lists prepare as their slots: four FireMode slots, three rate slots, five tags; the firing sound
    -- as its three event slots and its MIDI flag.
    local SLOTS={['fire_mode.modes']=3,['fire_rate.modes']=2,['presentation.traits']=4,
     ['presentation.armor_penetration']=4,['weapon.sound']=3}
    local expected=#batch.changes
    for _,change in ipairs(batch.changes)do expected=expected+(SLOTS[change.field]or 0)end
    assert(#plan.changes==expected,'physical support field count changed')
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
