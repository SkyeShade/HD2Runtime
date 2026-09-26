"""Build the external read-only HD2Runtime snapshot capture diagnostic."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

from hd2_archive import ARCHIVE_NAME,make_archive,resource_hash,lua_resource

ROOT=Path(__file__).resolve().parents[1]
ENTRY='mods/skyeshade/hd2runtime_snapshot_capture'


def revision(require_clean=True):
    if require_clean and subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT).strip():
        raise RuntimeError('Commit source changes before building a commit-identified snapshot ZIP')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def resources():
    found={ENTRY:(ROOT/'snapshot_capture/addon.lua').read_bytes()}
    body=b'\n'.join(found.values())
    for token in (b'VirtualProtect',b'WriteProcessMemory',b'ffi.',b'windows_write',b'guarded_write'):
        if token in body:raise ValueError('Disallowed snapshot package capability: '+token.decode())
    return found


def main():
    commit=revision();result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
        cwd=ROOT,capture_output=True,text=True)
    (ROOT/'build').mkdir(exist_ok=True);(ROOT/'build/snapshot-capture-tests.txt').write_text(result.stdout+result.stderr)
    print(result.stderr,end='')
    if result.returncode:raise RuntimeError('Regression tests failed')
    if revision()!=commit:raise RuntimeError('Source revision changed during validation')
    version=(ROOT/'VERSION').read_text().strip();config=json.loads((ROOT/'snapshot_capture/hd2runtime.json').read_text())
    sources=resources();archive=make_archive({resource_hash(k):lua_resource(v)for k,v in sources.items()})
    description=f'Read-only incremental process snapshot capture. Requires external HD2Runtime {version}+.'
    manifest={'Version':1,'Guid':config['guid'],'Name':config['name']+' '+version,'Description':description,
        'Options':[{'Name':'Snapshot capture','Description':description,'Include':['capture']}]}
    report={'version':version,'commit':commit,'runtime_bundled':False,'mode':'read_only','writes':0,
        'protection_changes':0,'deployed':False,'game_launched':False,'snapshot_format':1,
        'packaged_resources':sorted(sources)}
    files={'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),
        'hd2runtime.json':(json.dumps(config,indent=2)+'\n').encode(),
        'capture/'+ARCHIVE_NAME:archive,'capture/'+ARCHIVE_NAME+'.stream':b'',
        'capture/'+ARCHIVE_NAME+'.gpu_resources':b'','README.md':(ROOT/'docs/snapshots.md').read_bytes(),
        'build-report.json':(json.dumps(report,indent=2)+'\n').encode(),
        'tests.txt':(ROOT/'build/snapshot-capture-tests.txt').read_bytes()}
    sys.path.insert(0,str(ROOT/'sdk'));import hd2
    path=ROOT/'build'/f'HD2Runtime-SnapshotCapture-{version}.zip';hd2.zip_files(path,files)
    report['zip']=path.name;report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest().upper()
    (ROOT/'build/snapshot-capture-build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(path);print('commit='+commit);print('sha256='+report['sha256'])


if __name__=='__main__':main()
