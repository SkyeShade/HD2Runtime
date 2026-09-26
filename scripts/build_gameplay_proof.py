"""Build the guarded JAR-5 AP4 proof. Never deploy or launch HD2."""
import hashlib
import json
import subprocess
import sys
import zipfile

import build
from build_live_validation import revision, verify_installed
from hd2_archive import ARCHIVE_NAME, make_archive, resource_hash, lua_resource

ROOT=build.ROOT
ENTRY='mods/skyeshade/hd2runtime_jar5_ap4'


def resources():
    sources={name:body for name,body in build.resources(writable=True).items()
             if not name.startswith('hd2runtime/examples/') and name!='mods/skyeshade/hd2runtime_report'}
    sources[ENTRY]=(ROOT/'proof/addon.lua').read_bytes()
    for name,body in sources.items():
        if b'tests/fixtures' in body:
            raise ValueError('Fixture dependency in '+name)
        for forbidden in (b'VirtualProtect',b'WriteProcessMemory'):
            if forbidden in body and name!='hd2runtime/runtime/windows_write':
                raise ValueError('Unexpected native write dependency: '+name)
    return sources


def main():
    commit=revision()
    installed=verify_installed()
    run=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
                       cwd=ROOT,capture_output=True,text=True)
    (ROOT/'build').mkdir(exist_ok=True)
    (ROOT/'build/gameplay-proof-tests.txt').write_text(run.stdout+run.stderr)
    print(run.stderr,end='')
    if run.returncode:
        raise RuntimeError('Tests failed; see build/gameplay-proof-tests.txt')
    assert revision()==commit,'Source changed during build'
    sources=resources()
    archive=make_archive({resource_hash(n):lua_resource(b) for n,b in sources.items()})
    version=(ROOT/'VERSION').read_text().strip()
    description='Guarded JAR-5 logical AP3 to AP4 proof. Requires Bingus Shared Loader v15+ / API 1.'
    manifest={'Version':1,'Guid':'409256a5-fad4-4f67-bcce-bd7600eca620',
        'Name':'HD2Runtime '+version+' JAR-5 AP4 Gameplay Proof','Description':description,
        'Options':[{'Name':'Guarded JAR-5 AP4','Description':description,'Include':['proof']}]}
    report={'version':version,'commit':commit,'mode':'guarded_patch','deployed':False,'game_launched':False,
        'live_gameplay_status':'not run','fixture_fallback':'disabled','installed_files':installed,
        'packaged_resources':sorted(sources),'tests':'passed; see tests.txt',
        'patch':{'id':'jar5-ap4','resource':'0x80F1A156D9FA1E36','projectile_type':177,
                 'damage_type':153,'field':'armor_penetration','expect':3,'value':4,
                 'u32_offsets':[12,16,20],'preserved_u32_offset':24,'write_width':12,
                 'protection_scope':'one target data page, only if originally read-only'}}
    files={'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),
        'proof/'+ARCHIVE_NAME:archive,'proof/'+ARCHIVE_NAME+'.stream':b'',
        'proof/'+ARCHIVE_NAME+'.gpu_resources':b'',
        'README.md':(ROOT/'docs/guarded-patch.md').read_bytes(),
        'provenance.json':(ROOT/'docs/provenance.json').read_bytes(),
        'build-report.json':(json.dumps(report,indent=2)+'\n').encode(),
        'tests.txt':(ROOT/'build/gameplay-proof-tests.txt').read_bytes()}
    path=ROOT/'build'/f'HD2Runtime-{version}-jar5-ap4-gameplay-proof.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as package:
        for name,content in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            package.writestr(info,content)
    report['zip']=path.name
    report['zip_sha256']=hashlib.sha256(path.read_bytes()).hexdigest().upper()
    (ROOT/'build/gameplay-proof-build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(path)
    print('commit='+commit)
    print('sha256='+report['zip_sha256'])


if __name__=='__main__':
    main()
