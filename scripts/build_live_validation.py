"""Build the standalone live read-only report; no deployment or game launch.

Only local HD2Runtime source and the installed files' disk hashes are read.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

import build
from hd2_archive import ARCHIVE_NAME, make_archive, resource_hash, lua_resource
from reference_format import lua

ROOT=Path(__file__).resolve().parents[1]
ENTRY='mods/skyeshade/hd2runtime_live_validation'


def resources(commit='UNCOMMITTED_TEST_INPUT'):
    sources={name:body for name,body in build.resources().items()
             if not name.startswith('hd2runtime/examples/') and name!='mods/skyeshade/hd2runtime_report'}
    for path in sorted((ROOT/'validation').glob('*.lua')):
        if path.name!='addon.lua':
            sources['hd2runtime/validation/'+path.stem]=path.read_bytes()
    sources[ENTRY]=(ROOT/'validation/addon.lua').read_bytes()
    sources['hd2runtime/validation/build_metadata']=('return '+lua({
        'version':(ROOT/'VERSION').read_text().strip(),'commit':commit,'mode':'read_only'})+'\n').encode()
    for name,body in sources.items():
        for forbidden in (b'VirtualProtect',b'WriteProcessMemory',b'ffi.copy',b'ffi.fill',b'tests/fixtures'):
            if forbidden in body:
                raise ValueError('Disallowed capability/input in '+name)
    return sources


def verify_installed():
    game=Path(os.environ.get('HD2_GAME_ROOT',r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2'))
    pinned=json.loads((ROOT/'schemas/build_files.json').read_text())['files']
    result={}
    for relative,spec in pinned.items():
        with (game/relative).open('rb') as file:
            digest=hashlib.file_digest(file,'sha256').hexdigest().upper()
        result[relative]={'expected':spec['sha256'],'actual':digest,'matches':digest==spec['sha256']}
    if not all(item['matches'] for item in result.values()):
        raise RuntimeError('Installed build differs from pinned profile: '+json.dumps(result))
    return result


def revision():
    changed=subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT)
    if changed.strip():
        raise RuntimeError('Commit source changes before building a commit-identified validation ZIP')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def main():
    commit=revision()
    installed=verify_installed()
    result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
                          cwd=ROOT,capture_output=True,text=True)
    (ROOT/'build').mkdir(exist_ok=True)
    (ROOT/'build/live-validation-tests.txt').write_text(result.stdout+result.stderr)
    print(result.stderr,end='')
    if result.returncode:
        raise RuntimeError('Regression tests failed; see build/live-validation-tests.txt')
    if revision()!=commit:
        raise RuntimeError('Source revision changed during validation')
    version=(ROOT/'VERSION').read_text().strip()
    sources=resources(commit)
    archive=make_archive({resource_hash(name):lua_resource(body) for name,body in sources.items()})
    description='Read-only live ownership/value report. Requires Bingus Shared Loader v15+ / API 1.'
    manifest={'Version':1,'Guid':'409256a5-fad4-4f67-bcce-bd7600eca620',
        'Name':'HD2Runtime '+version+' Live Validation','Description':description,
        'Options':[{'Name':'Live read-only validation','Description':description,'Include':['validation']}]}
    report={'version':version,'commit':commit,'mode':'read_only','installed_files':installed,
        'packaged_resources':sorted(sources),'successfully_resolved_live':[],
        'live_test_status':'not run; deployment and HD2 launch excluded',
        'fixture_only_runtime_adapters':[],
        'limited_fixture_coverage':{'core/stratagem.lua':'saved live relay row; synthetic surrounding groups/table'},
        'tests':'passed; see live-validation-tests.txt','deployed':False,'game_launched':False,
        'writes':0,'protection_changes':0}
    files={'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),
        'validation/'+ARCHIVE_NAME:archive,
        'validation/'+ARCHIVE_NAME+'.stream':b'',
        'validation/'+ARCHIVE_NAME+'.gpu_resources':b'',
        'README.md':(ROOT/'docs/live-validation.md').read_bytes(),
        'provenance.json':(ROOT/'docs/provenance.json').read_bytes(),
        'build-report.json':(json.dumps(report,indent=2)+'\n').encode(),
        'tests.txt':(ROOT/'build/live-validation-tests.txt').read_bytes()}
    path=ROOT/'build'/f'HD2Runtime-{version}-live-validation.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as package:
        for name,content in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            package.writestr(info,content)
    report['zip']=path.name
    report['zip_sha256']=hashlib.sha256(path.read_bytes()).hexdigest().upper()
    (ROOT/'build/live-validation-build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(path)
    print('commit='+commit)
    print('sha256='+report['zip_sha256'])


if __name__=='__main__':
    main()
