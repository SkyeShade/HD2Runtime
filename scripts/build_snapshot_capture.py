"""Build the external read-only HD2Runtime snapshot capture diagnostic.

  py scripts/build_snapshot_capture.py                      # capture 60 s after the game loads (unchanged)
  py scripts/build_snapshot_capture.py --armed [--output D] # capture only when `py hd2.py snapshot arm` asks
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

from hd2_archive import ARCHIVE_NAME,make_archive,resource_hash,lua_resource

ROOT=Path(__file__).resolve().parents[1]
ENTRY='mods/skyeshade/hd2runtime_snapshot_capture'
# The armed variant is a separate resource and manager entry, so it never also runs the 60-second capture.
ARMED={'entry':'mods/skyeshade/hd2runtime_snapshot_armed','source':'snapshot_capture/armed_addon.lua',
    'name':'HD2Runtime Snapshot Capture (Armed)','guid':'cddcc06b-1052-59c7-93c2-669aa1d20e7d',
    'zip':'HD2Runtime-SnapshotCaptureArmed'}


def revision(require_clean=True):
    if require_clean and subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT).strip():
        raise RuntimeError('Commit source changes before building a commit-identified snapshot ZIP')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def resources(armed=False):
    found={ARMED['entry']:(ROOT/ARMED['source']).read_bytes()}if armed else{ENTRY:(ROOT/'snapshot_capture/addon.lua').read_bytes()}
    body=b'\n'.join(found.values())
    for token in (b'VirtualProtect',b'WriteProcessMemory',b'ffi.',b'windows_write',b'guarded_write'):
        if token in body:raise ValueError('Disallowed snapshot package capability: '+token.decode())
    return found


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--armed',action='store_true',help='build the armed variant (captures only on request)')
    parser.add_argument('--output',type=Path,default=ROOT/'build',help='output folder (default build/)')
    args=parser.parse_args(argv)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    commit=revision();result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
        cwd=ROOT,capture_output=True,text=True)
    (out/'snapshot-capture-tests.txt').write_text(result.stdout+result.stderr)
    print(result.stderr,end='')
    if result.returncode:raise RuntimeError('Regression tests failed')
    if revision()!=commit:raise RuntimeError('Source revision changed during validation')
    version=(ROOT/'VERSION').read_text().strip();config=json.loads((ROOT/'snapshot_capture/hd2runtime.json').read_text())
    if args.armed:
        config=dict(config,name=ARMED['name'],resource=ARMED['entry'],guid=ARMED['guid'])
    sources=resources(args.armed);archive=make_archive({resource_hash(k):lua_resource(v)for k,v in sources.items()})
    description=(f'Armed read-only process snapshot capture: captures only when `py hd2.py snapshot arm` asks. '
        f'Requires external HD2Runtime {version}+ with hd2.snapshot_control.' if args.armed else
        f'Read-only incremental process snapshot capture. Requires external HD2Runtime {version}+.')
    manifest={'Version':1,'Guid':config['guid'],'Name':config['name']+' '+version,'Description':description,
        'Options':[{'Name':'Snapshot capture','Description':description,'Include':['capture']}]}
    report={'version':version,'commit':commit,'variant':'armed'if args.armed else'timed','runtime_bundled':False,
        'mode':'read_only','writes':0,
        'protection_changes':0,'deployed':False,'game_launched':False,'snapshot_format':1,
        'packaged_resources':sorted(sources)}
    files={'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),
        'hd2runtime.json':(json.dumps(config,indent=2)+'\n').encode(),
        'capture/'+ARCHIVE_NAME:archive,'capture/'+ARCHIVE_NAME+'.stream':b'',
        'capture/'+ARCHIVE_NAME+'.gpu_resources':b'','README.md':(ROOT/'docs/snapshots.md').read_bytes(),
        'build-report.json':(json.dumps(report,indent=2)+'\n').encode(),
        'tests.txt':(out/'snapshot-capture-tests.txt').read_bytes()}
    sys.path.insert(0,str(ROOT/'sdk'));import hd2
    name=ARMED['zip']if args.armed else'HD2Runtime-SnapshotCapture'
    path=out/f'{name}-{version}.zip';hd2.zip_files(path,files)
    report['zip']=path.name;report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest().upper()
    (out/(('snapshot-capture-armed' if args.armed else 'snapshot-capture')+'-build-report.json')).write_text(
        json.dumps(report,indent=2)+'\n')
    print(path);print('commit='+commit);print('sha256='+report['sha256'])


if __name__=='__main__':main()
