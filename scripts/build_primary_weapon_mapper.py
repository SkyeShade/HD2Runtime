"""Build the external, read-only Primary Weapon Runtime Mapper diagnostic."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

import build
import import_primary_weapons
from hd2_archive import ARCHIVE_NAME, make_archive, resource_hash, lua_resource

ROOT=Path(__file__).resolve().parents[1]
ENTRY='mods/skyeshade/hd2runtime_primary_weapon_mapper'


def revision(require_clean=True):
    if require_clean:
        changed=subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT)
        if changed.strip():raise RuntimeError('Commit source changes before building a commit-identified mapper ZIP')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def resources(commit='UNCOMMITTED_TEST_INPUT'):
    found={}
    for path in sorted((ROOT/'primary_mapper').glob('*.lua')):
        if path.name!='addon.lua':found['hd2runtime/primary_mapper/'+path.stem]=path.read_bytes()
    found['hd2runtime/primary_mapper/build_metadata']=(
        "return {commit="+json.dumps(commit)+"}\n").encode()
    found[ENTRY]=(ROOT/'primary_mapper/addon.lua').read_bytes()
    for name,body in found.items():
        for forbidden in (b'VirtualQuery',b'VirtualProtect',b'WriteProcessMemory',b'ReadProcessMemory',
                          b'ffi.',b'windows_write',b'tests/fixtures',b'core/guarded_write'):
            if forbidden in body:raise ValueError('Disallowed diagnostic capability/input in '+name)
    return found


def main():
    import_primary_weapons.generate(check=True)
    commit=revision()
    run=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
                       cwd=ROOT,capture_output=True,text=True)
    (ROOT/'build').mkdir(exist_ok=True)
    (ROOT/'build/primary-weapon-mapper-tests.txt').write_text(run.stdout+run.stderr)
    print(run.stderr,end='')
    if run.returncode:raise RuntimeError('Regression tests failed')
    if revision()!=commit:raise RuntimeError('Source revision changed during validation')
    version=(ROOT/'VERSION').read_text().strip()
    sources=resources(commit)
    archive=make_archive({resource_hash(name):lua_resource(body) for name,body in sources.items()})
    config=json.loads((ROOT/'primary_mapper/hd2runtime.json').read_text())
    description=f'Read-only primary weapon mapper. Requires external HD2Runtime {version}+ and Bingus Shared Loader.'
    manifest={'Version':1,'Guid':config['guid'],'Name':config['name']+' '+version,
        'Description':description,'Options':[{'Name':'Primary weapon mapper','Description':description,
        'Include':['mapper']}]}
    report={'version':version,'commit':commit,'wiki_weapon_count':55,
        'runtime_bundled':False,'mode':'read_only','writes':0,'protection_changes':0,
        'fixture_fallback':'disabled','deployed':False,'game_launched':False,
        'packaged_resources':sorted(sources)}
    files={'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),
        'hd2runtime.json':(json.dumps(config,indent=2)+'\n').encode(),
        'mapper/'+ARCHIVE_NAME:archive,'mapper/'+ARCHIVE_NAME+'.stream':b'',
        'mapper/'+ARCHIVE_NAME+'.gpu_resources':b'',
        'README.md':(ROOT/'docs/primary-weapon-runtime-mapper.md').read_bytes(),
        'build-report.json':(json.dumps(report,indent=2)+'\n').encode(),
        'tests.txt':(ROOT/'build/primary-weapon-mapper-tests.txt').read_bytes()}
    sys.path.insert(0,str(ROOT/'sdk'))
    import hd2
    path=ROOT/'build'/f'HD2Runtime-PrimaryWeaponRuntimeMapper-{version}.zip'
    hd2.zip_files(path,files)
    report['zip']=path.name;report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest().upper()
    (ROOT/'build/primary-weapon-mapper-build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(path);print('commit='+commit);print('sha256='+report['sha256'])


if __name__=='__main__':main()
