"""Publish reviewed mission identities and timers; discovery evidence stays private."""
import argparse
import json
from pathlib import Path
from reference_format import lua
ROOT=Path(__file__).resolve().parents[1]
def generate(check=False):
    d=json.loads((ROOT/'research/mission-timers-F5FEE03DCFDB.json').read_text(encoding='utf8'))
    runtime={k:d[k] for k in ('build','gameDllSha256','imageSize','layout','sources','missions','pins','limitations')}
    public={'schemaVersion':1,'runtimeVersion':(ROOT/'VERSION').read_text(encoding='utf-8').strip(),'field':{'id':'mission.duration_seconds','unit':'seconds',
        'type':'number','min':60,'max':2500},'limitations':d['limitations'],'missions':[]}
    for m in d['missions']:
        s=d['sources'][m['source']]
        public['missions'].append({k:m[k] for k in ('id','name','faction','description','nameSource')}|
            {'timerGroup':m['source'],'durationSeconds':s['currentDefault'],'sharedWith':s['missions']})
    outputs={'domains/missions.lua':'-- Generated mission catalogue. Do not edit.\nreturn '+lua(runtime)+'\n',
        'sdk/MissionCapabilities.json':json.dumps(public,indent=2,ensure_ascii=False)+'\n'}
    changed=[]
    for name,body in outputs.items():
        p=ROOT/name
        if not p.exists() or p.read_text(encoding='utf8')!=body:
            changed.append(name)
            if not check:p.write_text(body,encoding='utf8')
    return changed
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    result=generate(a.check);print('\n'.join(result));raise SystemExit(bool(result) if a.check else 0)
