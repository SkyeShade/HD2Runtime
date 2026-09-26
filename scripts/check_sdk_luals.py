"""Validate real LuaLS hover/completion without an IDE, game, or deployment."""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parents[1]


def check(server,workspace=None):
    if workspace is None:
        workspace=ROOT/'build/luals-sdk-probe';workspace.mkdir(parents=True,exist_ok=True)
        config={'runtime.version':'LuaJIT','workspace.library':[(ROOT/'sdk/stubs').as_posix()],
                'workspace.checkThirdParty':False,'runtime.path':['?.lua','?/init.lua']}
        (workspace/'.luarc.json').write_text(json.dumps(config))
        label='sdk'
    else:
        workspace=Path(workspace).resolve()
        if not (workspace/'.luarc.json').is_file():raise RuntimeError('Workspace has no .luarc.json: '+str(workspace))
        label='starter'
    logs=ROOT/'build'/('luals-'+label+'-logs');meta=ROOT/'build'/('luals-'+label+'-meta')
    process=subprocess.Popen([str(Path(server).resolve()),'--logpath='+str(logs),
        '--metapath='+str(meta)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    messages=queue.Queue();counter=0
    def consume():
        try:
            while True:
                headers={}
                while True:
                    line=process.stdout.readline()
                    if not line:return
                    if line in (b'\r\n',b'\n'):break
                    name,value=line.decode().split(':',1);headers[name.lower()]=value.strip()
                messages.put(json.loads(process.stdout.read(int(headers['content-length']))))
        except Exception as error:messages.put({'reader_error':str(error)})
    threading.Thread(target=consume,daemon=True).start()
    def send(message):
        data=json.dumps({'jsonrpc':'2.0',**message}).encode()
        process.stdin.write(('Content-Length: '+str(len(data))+'\r\n\r\n').encode()+data);process.stdin.flush()
    def notify(method,params):send({'method':method,'params':params})
    def request(method,params):
        nonlocal counter
        counter+=1;identifier=counter;send({'id':identifier,'method':method,'params':params})
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            message=messages.get(timeout=max(.01,deadline-time.monotonic()))
            if message.get('id')==identifier and 'method' not in message:
                if 'error' in message:raise RuntimeError(message['error'])
                return message.get('result')
            if 'method' in message and 'id' in message:
                result=None
                if message['method']=='workspace/configuration':result=[None for _ in message['params']['items']]
                send({'id':message['id'],'result':result})
            if 'reader_error' in message:raise RuntimeError(message)
        raise RuntimeError('LuaLS request timed out: '+method)
    try:
        initialized=request('initialize',{'processId':None,'rootUri':workspace.as_uri(),
            'capabilities':{},'workspaceFolders':[{'uri':workspace.as_uri(),'name':'SDKProbe'}]})
        notify('initialized',{})
        probes=[('weapon',"hd2.weapon('JAR-5 Dominator')",'HD2Weapon'),
                ('projectile','weapon:projectile()','HD2Projectile'),
                ('damage','projectile:damage()','HD2DamageProfile'),
                ('vehicle',"hd2.vehicle('Bastion')",'HD2Vehicle'),
                ('health','vehicle:health()','HD2HealthComponent'),
                ('stratagem',"hd2.stratagem('Shield Relay')",'HD2Stratagem'),
                ('shield','stratagem:shield()','HD2Shield'),
                ('payload','stratagem:payload()','HD2Payload'),
                ('equipment',"hd2.equipment('Jump Pack')",'HD2Equipment'),
                ('recharge','equipment:recharge()','HD2RechargeComponent'),
                ('jumppack','equipment:jumppack()','HD2JumppackComponent'),
                ('orbital',"hd2.stratagem('Orbital Laser'):orbital()",'HD2OrbitalAbility')]
        source="local hd2=require('mods/skyeshade/hd2runtime')\n"+''.join(
            'local '+name+'='+expression+'\n' for name,expression,_ in probes)+'local field=hd2.fields.damage.\n'
        uri=(workspace/'probe.lua').as_uri()
        notify('textDocument/didOpen',{'textDocument':{'uri':uri,'languageId':'lua','version':1,'text':source}})
        hovers={}
        for line,(_,_,expected) in enumerate(probes,1):
            deadline=time.monotonic()+10
            while True:
                result=request('textDocument/hover',{'textDocument':{'uri':uri},'position':{'line':line,'character':7}})
                if result and 'Workspace loading' not in json.dumps(result):break
                if time.monotonic()>=deadline:break
                time.sleep(.05)
            assert expected in json.dumps(result),'Missing hover type '+expected+': '+json.dumps(result)
            hovers[expected]=result
        def complete(line,text):
            result=request('textDocument/completion',{'textDocument':{'uri':uri},
                'position':{'line':line,'character':len(text)},'context':{'triggerKind':1}})
            items=result.get('items',[]) if isinstance(result,dict) else result or []
            return [item['label'] for item in items]
        fields=complete(len(probes)+1,'local field=hd2.fields.damage.')
        assert 'armor_penetration' in fields,'Missing damage field completion: '+str(fields)
        changed=source.rsplit('local field=',1)[0]+'local next=weapon:\n'
        notify('textDocument/didChange',{'textDocument':{'uri':uri,'version':2},'contentChanges':[{'text':changed}]})
        methods=complete(len(probes)+1,'local next=weapon:')
        assert any('projectile' in label for label in methods),'Missing method completion: '+str(methods)
        report={'server':initialized.get('serverInfo'),'workspace':label,
                'hovers':hovers,'field_completions':fields,
                'method_completions':methods,'manual_rider_ui_test':False,'game_launched':False}
        (ROOT/'build'/('luals-'+label+'-report.json')).write_text(json.dumps(report,indent=2)+'\n')
        print('LuaLS typed hover and completion passed: '+', '.join(hovers))
        print('Damage field and weapon method completion passed')
        request('shutdown',None);notify('exit',None)
        return report
    finally:
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',required=True,type=Path)
    parser.add_argument('--workspace',type=Path)
    args=parser.parse_args()
    check(args.server,args.workspace)
