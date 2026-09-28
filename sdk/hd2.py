"""HD2Runtime authoring tools: offline inspection, new projects, IDE setup and build."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import uuid
import zipfile

SDK=Path(__file__).resolve().parent
MODULE='mods/skyeshade/hd2runtime'


def database(): return json.loads((SDK/'metadata.json').read_text())


def valid_resource(name):
    return (isinstance(name,str) and re.fullmatch(r'mods/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)+',name)
            and name not in (MODULE,'mods/codex/loader') and not name.startswith(MODULE+'/')
            and len(('-- HD2-Addon: '+name+'\n').encode())<=256)


def inspect(kind,name):
    schema=database()
    if kind=='type':
        matches=[(k,r) for k,r in schema['resources'].items() if any(
            name in (domain,schema['types'][domain]['name'],schema['types'][domain]['class']) for domain in r['domains'])]
        selected=[d for d,t in schema['types'].items() if name in (d,t['name'],t['class'])]
    else:
        matches=[(k,r) for k,r in schema['resources'].items() if r['kind']==kind and name in r['aliases']]
        selected=None
    if not matches and kind=='weapon' and (SDK/'PlayerWeaponAuthoringCapabilities.json').is_file():
        capabilities=json.loads((SDK/'PlayerWeaponAuthoringCapabilities.json').read_text())
        weapon=next((entry for entry in capabilities['weapons'] if entry['name']==name),None)
        if weapon:
            return {'mode':'offline_authoring_capabilities','current_process_read':False,
                'schema_version':capabilities['schemaVersion'],'runtime_version':capabilities['hd2RuntimeVersion'],
                'evidence_note':capabilities['fieldDefinitions'][0].get('reason') or
                    'Snapshot-derived reviewed authoring metadata; current ownership is resolved in-game.',
                'resources':[],'authoringWeapon':weapon}
    if not matches:raise ValueError('Unknown mapped '+kind+': '+name)
    return {'mode':'offline_schema','current_process_read':False,'schema_version':schema['schema_version'],
            'runtime_version':schema['runtime_version'],'evidence_note':schema['evidence_note'],
            'resources':[{**{n:v for n,v in r.items() if n!='fields'},'key':k,
                          'fields':{n:f for n,f in r['fields'].items() if selected is None or f['domain'] in selected}}
                         for k,r in matches]}


def format_inspection(result):
    schema=database();lines=['HD2Runtime '+result['runtime_version']+' | offline schema (no live process read)']
    if result.get('authoringWeapon'):
        weapon=result['authoringWeapon']
        lines+=['',weapon['name']+'  '+', '.join(weapon['resources']),
            '  family: '+', '.join(weapon['implementationFamilies'])]
        for field in weapon['fields']:
            if field.get('aliasOf'):
                access='deprecated alias; write accepted' if field.get('acceptedForWrites') else 'deprecated read-only alias'
            else:access='editable' if field['editable'] else 'read-only'
            lines+=['  '+field['semanticFieldId']+'  '+field['type']+'  '+access
                +'  default='+str(field['currentDefault'])+'  scope='+field['writeScope']]
            if field.get('aliasOf'):lines+=['    alias_of='+field['aliasOf']]
            if field.get('reason'):lines+=['    '+field['reason']]
        lines+=['',result['evidence_note']]
        return '\n'.join(lines)
    for r in result['resources']:
        lines+=['',r['label']+'  '+r['resource']]
        for domain,t in schema['types'].items():
            fields=[f for f in r['fields'].values() if f['domain']==domain]
            if not fields:continue
            lines+=['  '+t['name']]
            for f in fields:
                evidence=', '.join(k for k in schema['evidence_categories'] if f['evidence'][k])
                access='read/write (reviewed transition only)' if f['writable'] else 'read-only'
                lines+=['    '+f['name']+'  '+f['value_type']+'  '+access+'  baseline='+str(f['expected']),
                        '      '+evidence+'; source='+f['evidence']['source']]
                if f['evidence'].get('prior_live_confirmation'):lines+=['      prior_live_confirmation=true; current_live_ownership_proven=false']
                lines+=['      range='+json.dumps(f['semantic_range'])+'; enum='+str(f['enum'])]
    lines+=['',result['evidence_note']]
    return '\n'.join(lines)


def write_json(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def configure(project,sdk=SDK):
    project=Path(project).resolve();sdk=Path(sdk).resolve()
    if not (sdk/'metadata.json').is_file() or not (sdk/'stubs/mods/skyeshade/hd2runtime.lua').is_file():
        raise ValueError('Expected an unpacked HD2Runtime SDK directory')
    path=project/'hd2runtime.json';config=json.loads(path.read_text())
    try: relative=Path(os.path.relpath(sdk,project)).as_posix()
    except ValueError:relative=sdk.as_posix()
    config['sdk']=relative;write_json(path,config)
    luarc=project/'.luarc.json'
    options=json.loads(luarc.read_text()) if luarc.exists() else {}
    previous=config.get('ide_library')
    library=relative+'/stubs'
    options['workspace.library']=[x for x in options.get('workspace.library',[]) if x!=previous]
    if library not in options['workspace.library']:options['workspace.library'].append(library)
    options.update({'runtime.version':'LuaJIT','runtime.path':['?.lua','?/init.lua'],
                    'workspace.checkThirdParty':False})
    config['ide_library']=library;write_json(path,config);write_json(luarc,options)


def new_project(path,name,template='fire_rate',sdk=SDK):
    if not valid_resource(name):
        raise ValueError('Use a unique mods/author/mod_name resource')
    path=Path(path).resolve()
    if path.exists():raise ValueError('Refusing to overwrite an existing project: '+str(path))
    source=SDK/'templates'/template/'addon.lua'
    if not source.is_file():raise ValueError('Unknown template: '+template)
    schema=database()
    path.mkdir(parents=True)
    (path/'src').mkdir();(path/'tests').mkdir()
    (path/'VERSION').write_text('0.1.0\n')
    (path/'src/addon.lua').write_text(source.read_text(),encoding='utf-8')
    (path/'build.py').write_bytes((SDK/'templates/build.py').read_bytes())
    (path/'tests/test_package.py').write_bytes((SDK/'templates/test_package.py').read_bytes())
    (path/'.gitignore').write_text('build/\n__pycache__/\n*.pyc\n.idea/\n')
    write_json(path/'hd2runtime.json',{'format':1,'name':path.name,'resource':name,
        'guid':str(uuid.uuid5(uuid.NAMESPACE_URL,'hd2runtime:'+name)),
        'requires':{'bingus':{'min_release':15,'api':1},
                    'hd2runtime':{'min_version':schema['runtime_version'],'api':schema['api_version'],'module':MODULE}}})
    configure(path,sdk)
    (path/'README.md').write_text('# '+path.name+'\n\nRequires Bingus Shared Loader v15+ / API 1 and HD2Runtime '+schema['runtime_version']+'+ / API 1 installed once.\n\n'
        'This project contains only gameplay declarations. Do not copy the runtime or SDK stubs into src.\n\n'
        'Build: `python build.py`. Test: `python -m unittest discover -s tests -v`.\n\n'
        'The shared SDK path is in hd2runtime.json; `.luarc.json` references its stubs.\n'
        'After moving the SDK run `python <SDK>/hd2.py configure . --sdk <SDK>`.\n\n'
        'In Rider, configure Lua language tooling to index the shared stubs directory. LuaLS reads `.luarc.json`; other EmmyLua tooling may require adding that directory as a library manually.\n\n'
        'Players install Bingus, the standalone HD2Runtime package, and this mod. The mod explicitly requires HD2Runtime; no gameplay-mod priority ordering is needed. Dependency metadata is descriptive, not manager auto-installation.\n',encoding='utf-8')
    return path


def zip_files(path,files):
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w') as z:
        for name,content in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,content)


# Optional dependencies never gate loading; HD2Runtime degrades the features that need them.
OPTIONAL_MOD_OPTIONS_MENU={'min_version':'1.0.0','api':1,'bingus_min_release':18}
OPTIONS_NOTE=(' Optional: CowboyBingus Mod Options Menu v1+ (needs Bingus Shared Loader v18+) for in-game'
    ' settings; without it the settings use their defaults.')


def optional_dependencies(spec):
    optional=spec.get('optional')
    if optional is None:return {}
    if not isinstance(optional,dict) or set(optional)-{'mod_options_menu'}:
        raise ValueError('Unsupported optional dependency; only mod_options_menu is supported')
    menu=optional.get('mod_options_menu')
    if menu is not None and (not isinstance(menu,dict) or menu.get('api')!=1
            or not re.fullmatch(r'\d+\.\d+\.\d+',str(menu.get('min_version','')))
            or not isinstance(menu.get('bingus_min_release'),int) or menu['bingus_min_release']<18
            or set(menu)!={'min_version','api','bingus_min_release'}):
        raise ValueError('mod_options_menu needs min_version, api 1 and bingus_min_release 18+')
    return optional


def build_project(project):
    from tools.hd2_archive import ARCHIVE_NAME, make_archive, resource_hash, lua_resource
    project=Path(project).resolve();spec=json.loads((project/'hd2runtime.json').read_text())
    name=spec['resource'];required=spec['requires'];version=(project/'VERSION').read_text().strip()
    if not valid_resource(name):
        raise ValueError('Reserved or invalid resource identity')
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('VERSION must contain major.minor.patch')
    if spec.get('format')!=1:raise ValueError('Unsupported hd2runtime.json format')
    if required['bingus']!={'min_release':15,'api':1} or required['hd2runtime']['module']!=MODULE or required['hd2runtime']['api']!=1:
        raise ValueError('Unsupported dependency contract')
    minimum=required['hd2runtime']['min_version']
    if not re.fullmatch(r'\d+\.\d+\.\d+',minimum):raise ValueError('Invalid minimum runtime version')
    optional=optional_dependencies(spec)
    # This wrapper checks runtime dependencies; it contains no HD2Runtime implementation.
    wrapper='-- HD2-Addon: '+name+'\n'+'''local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'Requires Bingus Shared Loader v15+ / API 1')
local hd2=require('mods/skyeshade/hd2runtime')
local function version(v)
    local a,b,c=tostring(v):match('^(%d+)%.(%d+)%.(%d+)$')
    assert(a,'Invalid HD2Runtime version');return tonumber(a),tonumber(b),tonumber(c)
end
local a,b,c=version(hd2.version)
local x,y,z=version('''+json.dumps(minimum)+''')
assert(hd2.api_version==1 and (a>x or a==x and (b>y or b==y and c>=z)),
    'HD2Runtime dependency version mismatch')
local key='HD2RuntimeMod:'..'''+json.dumps(name)+'''
local existing=rawget(_G,key)
if existing then return existing end
local function start()
'''
    sources={}
    for path in sorted((project/'src').rglob('*.lua')):
        if path.is_symlink() or not path.resolve().is_relative_to(project/'src'):
            raise ValueError('Source must be inside project/src')
        relative=path.relative_to(project/'src').with_suffix('').as_posix()
        resource=name if relative=='addon' else name+'/'+relative
        body=path.read_text(encoding='utf-8-sig')
        if '---@meta' in body or '-- HD2-Addon:' in body:raise ValueError('SDK stubs or extra declarations are not gameplay source')
        if relative=='addon':body=wrapper+body+"\nend\nlocal state=start() or true\nrawset(_G,key,state)\nreturn state\n"
        sources[resource]=body.encode()
    if name not in sources:raise ValueError('Missing src/addon.lua')
    archive=make_archive({resource_hash(k):lua_resource(v) for k,v in sources.items()})
    description='Requires Bingus Shared Loader v15+ / API 1 and HD2Runtime '+minimum+'+ / API 1; install dependencies separately.'
    if optional:description+=OPTIONS_NOTE
    manifest={'Version':1,'Guid':str(uuid.UUID(spec['guid'])),'Name':spec['name']+' '+version,'Description':description,
              'Options':[{'Name':spec['name'],'Description':description,'Include':['mod']}]}
    report={'resources':sorted(sources),'runtime_bundled':False,'sdk_stubs_bundled':False,
            'requires':required,'optional':optional,'deployed':False,'game_launched':False}
    files={'manifest.json':json.dumps(manifest,indent=2).encode(),
           'hd2runtime.json':json.dumps({k:v for k,v in spec.items() if k not in ('sdk','ide_library')},indent=2).encode(),
           'build-report.json':json.dumps(report,indent=2).encode(),'README.md':(project/'README.md').read_bytes(),
           'mod/'+ARCHIVE_NAME:archive,'mod/'+ARCHIVE_NAME+'.stream':b'','mod/'+ARCHIVE_NAME+'.gpu_resources':b''}
    path=project/'build'/(project.name+'-'+version+'.zip');zip_files(path,files)
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('inspect');p.add_argument('kind',choices=['weapon','vehicle','stratagem','equipment','type']);p.add_argument('name');p.add_argument('--json',action='store_true')
    p=sub.add_parser('new');p.add_argument('path',type=Path);p.add_argument('--name',required=True);p.add_argument('--template',choices=['fire_rate','projectile_damage'],default='fire_rate');p.add_argument('--sdk',type=Path,default=SDK)
    p=sub.add_parser('configure');p.add_argument('project',type=Path);p.add_argument('--sdk',type=Path,default=SDK)
    p=sub.add_parser('build');p.add_argument('project',type=Path)
    p=sub.add_parser('snapshot');snapshot_sub=p.add_subparsers(dest='snapshot_command',required=True)
    scan=snapshot_sub.add_parser('scan-weapons')
    scan.add_argument('snapshot',type=Path);scan.add_argument('wiki',type=Path)
    scan.add_argument('--output',type=Path);scan.add_argument('--historical-analysis',action='store_true')
    scan.add_argument('--lua-dll',type=Path,help='Path to the owned HD2 bin/lua51.dll')
    player_scan=snapshot_sub.add_parser('scan-player-weapons')
    player_scan.add_argument('snapshot',type=Path);player_scan.add_argument('wiki',type=Path)
    player_scan.add_argument('--output',type=Path);player_scan.add_argument('--summary-output',type=Path)
    player_scan.add_argument('--historical-analysis',action='store_true')
    player_scan.add_argument('--lua-dll',type=Path,help='Path to the owned HD2 bin/lua51.dll')
    support_scan=snapshot_sub.add_parser('scan-support-weapons')
    support_scan.add_argument('snapshot',type=Path);support_scan.add_argument('wiki',type=Path)
    support_scan.add_argument('--output',type=Path);support_scan.add_argument('--historical-analysis',action='store_true')
    support_scan.add_argument('--lua-dll',type=Path,help='Path to the owned HD2 bin/lua51.dll')
    args=parser.parse_args()
    try:
        if args.command=='inspect':
            result=inspect(args.kind,args.name);print(json.dumps(result,indent=2) if args.json else format_inspection(result))
        elif args.command=='new':print(new_project(args.path,args.name,args.template,args.sdk))
        elif args.command=='configure':configure(args.project,args.sdk);print('IDE configuration updated')
        elif args.command=='build':print(build_project(args.project))
        elif args.snapshot_command=='scan-weapons':
            from tools.snapshot_scan import scan
            output,mapping=scan(args.snapshot,args.wiki,args.output,args.historical_analysis,args.lua_dll)
            print(output);print(mapping)
        elif args.snapshot_command=='scan-player-weapons':
            from tools.snapshot_scan import scan_player_weapons
            output,mapping,summary=scan_player_weapons(args.snapshot,args.wiki,args.output,
                args.historical_analysis,args.lua_dll,args.summary_output)
            print(output);print(mapping);print(summary)
        else:
            from tools.snapshot_scan import scan_support_weapons
            output,mapping,summary,log=scan_support_weapons(args.snapshot,args.wiki,args.output,
                args.historical_analysis,args.lua_dll)
            print(output);print(mapping);print(summary);print(log)
    except (ValueError,KeyError,OSError,RuntimeError) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
