"""Resolve every reviewed writable player-weapon descriptor against an HD2 snapshot.

This deliberately stops before the guarded writer. It proves that the normal runtime
domain can freshly resolve ownership and expected bytes without exposing addresses.
"""
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

DEFAULT_SNAPSHOT=build_profile.SNAPSHOT
DEFAULT_OUTPUT=ROOT/'build/snapshot-results-authoring/PlayerWeaponWritePathValidation.json'


def lua(value):
    if isinstance(value,dict):return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '{'+','.join(lua(v) for v in value)+'}'
    if isinstance(value,bool):return'true'if value else'false'
    if value is None:return'nil'
    if isinstance(value,(int,float)):return repr(value)
    return json.dumps(str(value),ensure_ascii=False)


def module_sources():
    result={}
    for folder in ('api','core','runtime','schemas','domains','primary_mapper'):
        for path in sorted((ROOT/folder).glob('*.lua')):
            result['hd2runtime/'+path.relative_to(ROOT).with_suffix('').as_posix()]=path.read_text()
    return result


def validate(snapshot=DEFAULT_SNAPSHOT,output=DEFAULT_OUTPUT):
    snapshot=Path(snapshot).resolve();output=Path(output)
    if not snapshot.is_file():raise ValueError('Snapshot file not found: '+str(snapshot))
    capabilities=json.loads((ROOT/'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())
    audit=[]
    for weapon in capabilities['weapons']:
        batches=[]
        for field in (f for f in weapon['fields'] if f['acceptedForWrites']):
            backing=field['backing']
            identity=(backing['kind'],backing.get('component'),backing.get('settings'),
                backing.get('recordIndex'),backing.get('group'),backing.get('row'),
                backing['offset'],backing['width'])
            if field['type']=='projectile_reference':
                role=field['referenceRole']
                handle={'resource':'player_weapon','path':'projectile_reference',
                    'weapon':weapon['name'],'attack':role}
                change={'field':'attack.projectile','expect':handle,'value':handle}
                target={'resource':'player_weapon','path':'attack','weapon':weapon['name'],'attack':role}
            elif field['type']=='explosion_reference':
                role=field['referenceRole'];phase=field['referencePhase']
                handle={'resource':'player_weapon','path':('explosion'
                    if field['currentDefault']['explosionType'] else 'no_explosion'),'weapon':weapon['name'],
                    'attack':role,'phase':phase}
                change={'field':'terminal.explosion','expect':handle,'value':handle}
                target={'resource':'player_weapon','path':'terminal_action','weapon':weapon['name'],
                    'attack':role,'phase':phase}
            elif field['semanticFieldId'].startswith('explosion.'):
                parts=field['semanticFieldId'].split('.')
                role,phase=parts[1:3]
                change={'field':field['semanticFieldId'],'expect':field['currentDefault'],
                    'value':field['currentDefault']}
                target={'resource':'player_weapon','path':'explosion','weapon':weapon['name'],
                    'attack':role,'phase':phase}
            elif field.get('writeKind')=='reorder_native_mode_vector':
                destination=next(value for value in field['allowedValues']
                    if value!=field['currentDefault'])
                change={'field':field['semanticFieldId'],'expect':field['currentDefault'],
                    'value':destination,'validationOnly':True}
                target={'resource':'player_weapon','path':'weapon','weapon':weapon['name']}
            else:
                change={'field':field['semanticFieldId'],'expect':field['currentDefault'],
                    'value':field['currentDefault']}
                target={'resource':'player_weapon','path':'weapon','weapon':weapon['name']}
            force_single=field.get('writeKind')=='reorder_native_mode_vector'
            placed=False
            if force_single:
                batches.append({'target':target,'changes':[change],'identities':{identity},'exclusive':True})
                continue
            for batch in batches:
                if not batch.get('exclusive') and batch['target']==target and len(batch['changes'])<32 and identity not in batch['identities']:
                    batch['changes'].append(change);batch['identities'].add(identity);placed=True;break
            if not placed:batches.append({'target':target,'changes':[change],'identities':{identity}})
        audit.append({'name':weapon['name'],'blocked':weapon['ordinaryWritesBlocked'],
            'batches':[{'target':batch['target'],'changes':batch['changes']} for batch in batches]})
    sources=module_sources()
    preload='\n'.join('package.preload['+lua(name)+']=function(...) return assert(loadstring('
        +lua(body)+','+lua(name)+'))(...) end' for name,body in sources.items())
    program=preload+r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open('''+lua(str(snapshot))+r''',{
    expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
assert(source.module_hash(source.module(nil))==profile.exe_sha)
assert(source.module_hash(source.module('game.dll'))==profile.dll_sha)
local Reader=require('hd2runtime/runtime/reader')
local domain=require('hd2runtime/domains/player_weapon_writes')
local guarded=require('hd2runtime/core/guarded_transaction')
local audit='''+lua(audit)+r'''
local result={weapons=0,fields=0,blocked=0,failures={},writes=0,protectionChanges=0,
    fixtureFallback='disabled',mode='snapshot',fingerprints={exe=profile.exe_sha,dll=profile.dll_sha}}
for _,weapon in ipairs(audit)do
    if weapon.blocked then
        result.blocked=result.blocked+1
        local ok=pcall(domain.validate_patch,{id='duplicate-block',
            target={resource='player_weapon',path='weapon',weapon=weapon.name},
            field='weapon.fire_rate',expect=1,value=1})
        assert(not ok,'duplicate identity unexpectedly writable')
    else
        result.weapons=result.weapons+1
        for _,batch in ipairs(weapon.batches)do
            local changes=batch.changes
            if #changes>0 then
                local worker=coroutine.create(function()
                    local validation_only=changes[1].validationOnly
                    for _,change in ipairs(changes)do change.validationOnly=nil end
                    local spec=domain.validate_transaction({id='snapshot-write-audit',allow_shared=true,
                        allow_unverified_effect=true,target=batch.target,changes=changes})
                    local reader=Reader.new(source)
                    local resolved=domain.capture(source,reader,spec)
                    local plan=domain.prepare(resolved,reader,spec)
                    reader.verify()
                    if validation_only then
                        local labels={};for _,item in ipairs(plan.changes)do labels[#labels+1]=item.label end
                        assert(#plan.changes==2 and not plan.changes[1].already_desired,
                            'fire mode plan count='..#plan.changes..' already='..tostring(plan.changes[1].already_desired)
                            ..' labels='..table.concat(labels,','))
                    else
                        -- fire_mode.modes prepares as its four FireMode slots.
                        local expected=#changes
                        for _,change in ipairs(changes)do if change.field=='fire_mode.modes'then expected=expected+3 end end
                        assert(#plan.changes==expected)
                        local guarded_result=guarded.apply(source,plan)
                        assert(guarded_result.status=='ALREADY_DESIRED'and guarded_result.writes==0
                            and guarded_result.protection_changes==0 and guarded_result.protection_restored)
                    end
                    return #changes
                end)
                local ok,value
                repeat ok,value=coroutine.resume(worker) until not ok or coroutine.status(worker)=='dead'
                if not ok then
                    result.failures[#result.failures+1]={weapon=weapon.name,firstField=changes[1].field,error=tostring(value)}
                else result.fields=result.fields+value end
            end
        end
    end
end
source.close()
return require('hd2runtime/primary_mapper/json').encode(result)
'''
    result=json.loads(execute(program.encode()))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path,nargs='?',default=DEFAULT_SNAPSHOT)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args();result=validate(args.snapshot,args.output)
    print(json.dumps(result,indent=2))
    if result['failures']:raise SystemExit(1)
