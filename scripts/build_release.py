"""Build the installed-once runtime, authoring-only SDK, and independent examples."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import build
import generate_sdk
import generate_weapon_authoring
import generate_support_weapon_sdk
import generate_support_weapon_authoring
import generate_stratagem_authoring
import generate_weapon_composition
from build_live_validation import revision,verify_installed
from hd2_archive import ARCHIVE_NAME,make_archive,resource_hash,lua_resource

ROOT=build.ROOT
sys.path.insert(0,str(ROOT/'sdk'))
import hd2


def runtime_resources():
    resources={k:v for k,v in build.resources(writable=True).items()
               if not k.startswith('hd2runtime/examples/') and k!='mods/skyeshade/hd2runtime_report'}
    resources[hd2.MODULE]=(ROOT/'packaging/library.lua').read_bytes()
    return resources


def starter_files():
    return {path.relative_to(ROOT/'starter').as_posix():path.read_bytes()
            for path in sorted((ROOT/'starter').rglob('*')) if path.is_file()
            and 'build' not in path.relative_to(ROOT/'starter').parts}


def build_starter(version):
    path=ROOT/'build'/('HD2Runtime-ModTemplate-'+version+'.zip')
    hd2.zip_files(path,starter_files())
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--luals',type=Path,help='Optional LuaLS executable for real type/completion checks')
    args=parser.parse_args()
    generate_weapon_composition.generate(check=True)
    generate_support_weapon_sdk.generate(check=True)
    generate_support_weapon_authoring.generate(check=True)
    generate_stratagem_authoring.generate(check=True)
    generate_weapon_authoring.generate(check=True)
    generate_sdk.generate(check=True)
    schema=hd2.database();version=(ROOT/'VERSION').read_text().strip()
    assert version==schema['runtime_version'],'Version/schema mismatch'
    commit=revision();installed=verify_installed()
    run=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True)
    print(run.stderr,end='')
    if run.returncode:raise RuntimeError('Release tests failed: '+run.stdout)
    assert revision()==commit,'Source changed during build'
    report={'version':version,'commit':commit,'tests':run.stderr,'installed_files':installed,
            'deployed':False,'game_launched':False,'live_process_access':False,
            'prior_gameplay_confirmation':'User confirmed 0.4.0 live gameplay proof',
            'new_live_gameplay_test':False,'fixture_fallback':'disabled'}
    support_capabilities=json.loads((ROOT/'sdk/SupportWeaponAuthoringCapabilities.json').read_text())
    support_validation=json.loads((ROOT/'research/support-weapon-authoring-validation-F5FEE03DCFDB.json').read_text())
    report['support_weapon_authoring']=support_capabilities['summary']
    report['support_weapon_capability_contract']={
        'schemaVersion':support_capabilities['schemaVersion'],
        'contract':support_capabilities['contract'],
        'instanceAudit':support_capabilities['instanceAudit'],
        'backingObjects':len(support_capabilities['backingObjects']),
        'operationGroups':len(support_capabilities['operationGroups'])}
    report['support_weapon_snapshot_validation']=support_validation
    report['support_weapon_proof_packages']=[
        'SupportAMRProof','RecoillessProof','ArcThrowerProof','C4Proof']
    stratagem_capabilities=json.loads((ROOT/'sdk/StratagemAuthoringCapabilities.json').read_text())
    report['stratagem_authoring']=stratagem_capabilities['summary']
    report['stratagem_snapshot_validation']=json.loads(
        (ROOT/'validation/stratagem-authoring-snapshot.json').read_text())
    call_in_links=support_capabilities['supportCallInLinks']
    assert call_in_links==stratagem_capabilities['supportCallInLinks'],'Support call-in linkage diverged'
    assert call_in_links['audit']['bidirectionalMismatches']==0,'Support call-in linkage is one-way'
    report['support_call_in_linkage']=call_in_links['audit']
    report['stratagem_proof_packages']=['OrbitalLaserProof','OrbitalPrecisionProof',
        'OrbitalBarrageProof','EagleProof','SupportStratagemCooldownProof',
        'AntiTankEmplacementProof','ConventionalSentryProof','ExplosiveSentryProof',
        'UnusualSentryProof']
    if args.luals:
        from check_sdk_luals import check
        report['luals']={'sdk':check(args.luals),'starter':check(args.luals,ROOT/'starter')}
    spec=json.loads((ROOT/'hd2runtime.json').read_text());sources=runtime_resources()
    archive=make_archive({resource_hash(k):lua_resource(v) for k,v in sources.items()})
    description='Shared HD2Runtime API 1. Requires Bingus Shared Loader v15+ / API 1. Install once; no gameplay changes until a dependent mod requests them.'
    manifest={'Version':1,'Guid':spec['guid'],'Name':'HD2Runtime '+version,'Description':description,
              'Options':[{'Name':'Shared runtime','Description':description,'Include':['runtime']}]}
    report_bytes=(json.dumps(report,indent=2)+'\n').encode()
    runtime_zip=ROOT/'build'/('HD2Runtime-'+version+'-runtime.zip')
    hd2.zip_files(runtime_zip,{'manifest.json':json.dumps(manifest,indent=2).encode(),
        'hd2runtime.json':json.dumps(spec,indent=2).encode(),'runtime/'+ARCHIVE_NAME:archive,
        'runtime/'+ARCHIVE_NAME+'.stream':b'','runtime/'+ARCHIVE_NAME+'.gpu_resources':b'',
        'README.md':(ROOT/'sdk/README.md').read_bytes(),'build-report.json':report_bytes,
        'provenance.json':(ROOT/'docs/provenance.json').read_bytes()})
    sdk_zip=ROOT/'build'/('HD2Runtime-'+version+'-sdk.zip')
    sdk_files={p.relative_to(ROOT/'sdk').as_posix():p.read_bytes() for p in (ROOT/'sdk').rglob('*')
               if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    from tools.snapshot_scan import bundle_bytes
    sdk_files['tools/snapshot_scan_modules.json']=bundle_bytes()
    sdk_files['build-report.json']=report_bytes
    hd2.zip_files(sdk_zip,sdk_files)
    example_files={}
    starter_zip=build_starter(version)
    artifacts=[runtime_zip,sdk_zip,starter_zip]
    for project in sorted((ROOT/'examples/projects').iterdir()):
        if not project.is_dir():continue
        artifacts.append(hd2.build_project(project))
        for path in project.rglob('*'):
            if path.is_file() and not {'build','__pycache__','.idea'}.intersection(path.relative_to(project).parts):
                example_files[path.relative_to(ROOT/'examples/projects').as_posix()]=path.read_bytes()
    example_files['README.md']=b'Example source projects. Run python <SDK>/hd2.py configure <project> --sdk <SDK> after extraction, then python build.py. Install runtime once and each desired gameplay mod separately.\n'
    examples_zip=ROOT/'build'/('HD2Runtime-'+version+'-example-projects.zip')
    hd2.zip_files(examples_zip,example_files);artifacts.append(examples_zip)
    report['artifacts']=[{'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in artifacts]
    (ROOT/'build/sdk-release-report.json').write_text(json.dumps(report,indent=2)+'\n')
    for p in artifacts:print(p)
    print('commit='+commit)


if __name__=='__main__':main()
