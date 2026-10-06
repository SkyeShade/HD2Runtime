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


# SemVer 2.0 (MAJOR.MINOR.PATCH, optional -prerelease and +build), for the minimum HD2Runtime a mod requires.
SEMVER=r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?'


def wrap_addon(name,minimum,body,display=None):
    """The shipped addon resource: a dependency check, then the author's src/addon.lua run once per game session.
    The startup runs as the mod's own resource id (hd2.events.run_as), so every subscription, timer, keybind and
    action it registers belongs to the mod without passing the id; an older HD2Runtime without run_as runs it
    directly. The version check is SemVer (a prerelease is older than its release). When the installed HD2Runtime is
    too old, the wrapper tells it (hd2.compatibility, HD2Runtime 0.28.0+, which shows one update warning per session)
    and then fails closed as before. This wrapper checks runtime dependencies; it contains no HD2Runtime
    implementation."""
    return '-- HD2-Addon: '+name+'\n'+'''local loader=rawget(_G,'CowboyBingusModLoader')
assert(loader and loader.api==1 and type(loader.version)=='number' and loader.version>=16,
    'Requires Bingus Shared Loader v15+ / API 1')
local hd2=require('mods/skyeshade/hd2runtime')
local function semver(v)
    local core,pre=tostring(v):match('^([^%-+]+)%-?([^+]*)')
    local a,b,c=(core or''):match('^(%d+)%.(%d+)%.(%d+)$')
    assert(a,'Invalid HD2Runtime version: '..tostring(v))
    local ids={}
    for id in(pre~=''and pre..'.'or''):gmatch('([^%.]*)%.')do ids[#ids+1]=id end
    return {tonumber(a),tonumber(b),tonumber(c),ids}
end
local function order(p,q)
    local x,y=tonumber(p:match('^%d+$')),tonumber(q:match('^%d+$'))
    if x and y then return x<y and -1 or x>y and 1 or 0 end
    if x then return -1 end
    if y then return 1 end
    return p<q and -1 or p>q and 1 or 0
end
local function at_least(have,need)
    local x,y=semver(have),semver(need)
    for i=1,3 do if x[i]~=y[i]then return x[i]>y[i]end end
    local p,q=x[4],y[4]
    if#p==0 then return true end
    if#q==0 then return false end
    for i=1,math.max(#p,#q)do
        if p[i]==nil then return false end
        if q[i]==nil then return true end
        local o=order(p[i],q[i])
        if o~=0 then return o>0 end
    end
    return true
end
local minimum='''+json.dumps(minimum)+'''
local satisfied=hd2.api_version==1 and at_least(hd2.version,minimum)
if not satisfied and hd2.api_version==1 then
    local compatibility=type(hd2.compatibility)=='table'and hd2.compatibility.require_runtime
    if type(compatibility)=='function'then pcall(compatibility,'''+json.dumps(name)+''',minimum,'''+json.dumps(display or name)+''')end
end
assert(satisfied,'HD2Runtime dependency version mismatch')
local key='HD2RuntimeMod:'..'''+json.dumps(name)+'''
local existing=rawget(_G,key)
if existing then return existing end
local function start()
'''+body+'''
end
local run=type(hd2.events)=='table' and hd2.events.run_as
local state
if type(run)=='function' then state=run('''+json.dumps(name)+''',start) else state=start() end
state=state or true
rawset(_G,key,state)
return state
'''


def project_images(project):
    """{image id: PNG bytes} of the project's images/<id>.png (docs/custom-images.md), each checked as a 256 x 256
    icon; {} without images. Each becomes the mod's own icon family <resource>/images/<id> (texture and GUI material)
    in the mod's archive."""
    from tools.hd2_image import icon_pixels, valid_image_id
    folder=project/'images'
    if not folder.exists():return {}
    if folder.is_symlink() or not folder.is_dir():raise ValueError('images must be a folder inside the project')
    images={}
    for path in sorted(folder.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix!='.png':
            raise ValueError('images/ holds PNG files only (images/<id>.png): '+path.name)
        if not valid_image_id(path.stem):
            raise ValueError('image id must be 1 to 64 lowercase letters, digits or underscores: '+path.name)
        data=path.read_bytes()
        try:icon_pixels(data)
        except ValueError as error:raise ValueError('images/'+path.name+': '+str(error)) from None
        images[path.stem]=data
    return images


def image_preparations(spec,images):
    """{image id: 'auto' | 'raw'}: every image is prepared automatically (masks as given, any other picture converted
    to the game's icon masks) unless hd2runtime.json declares it raw: "images": {"<id>": "raw"}."""
    declared=spec.get('images')
    if declared is None:declared={}
    if not isinstance(declared,dict):raise ValueError('hd2runtime.json images must be {"<image id>": "raw"}')
    for image_id,mode in declared.items():
        if image_id not in images:raise ValueError('hd2runtime.json images names '+str(image_id)+', not in images/')
        if mode!='raw':raise ValueError('hd2runtime.json images: '+str(image_id)+' can only be declared "raw"')
    return {image_id:declared.get(image_id,'auto') for image_id in images}


IMAGE_CACHE='.image-cache'
CUSTOM_STRATAGEMS='custom_stratagems.json'


def compile_icon(project,png,mode):
    """(texture main part, GPU part, what was done, 'hit' | 'miss') of one editable PNG, through the project's build
    cache: build/.image-cache/<converter>-<mode>-<SHA-256 of the PNG>.bin. A cached texture is used while the PNG and
    the conversion rule are the same (and its own digest checks); otherwise it is compiled and cached again."""
    import hashlib
    from tools.hd2_image import MASKS_CONVERTER, prepare_icon, texture_main, bc1_mips, ICON_SIZE, ICON_MIPS
    source=hashlib.sha256(png).hexdigest()
    folder=Path(project)/'build'/IMAGE_CACHE
    path=folder/(MASKS_CONVERTER+'-'+mode+'-'+source+'.bin')
    if path.is_file():
        data=path.read_bytes()
        try:
            digest,size=data[:32],int.from_bytes(data[32:36],'little')
            label_size=int.from_bytes(data[36:38],'little')
            label=data[38:38+label_size].decode('utf-8')
            body=data[38+label_size:]
            if hashlib.sha256(data[32:]).digest()==digest and size<=len(body):
                return body[:size],body[size:],label,'hit'
        except (ValueError,UnicodeDecodeError):
            pass
    rgba,label=prepare_icon(png,mode)
    main,gpu=texture_main(ICON_SIZE,ICON_SIZE,ICON_MIPS),bc1_mips(ICON_SIZE,ICON_SIZE,rgba)
    encoded=label.encode('utf-8')
    rest=len(main).to_bytes(4,'little')+len(encoded).to_bytes(2,'little')+encoded+main+gpu
    folder.mkdir(parents=True,exist_ok=True)
    partial=path.with_suffix('.partial')
    partial.write_bytes(hashlib.sha256(rest).digest()+rest)
    partial.replace(path)
    return main,gpu,label,'miss'


def project_icon_resources(project,spec,images=None,record=False):
    """The icon families of a project's editable images (docs/custom-images.md): ({(resource type, name hash): parts},
    {image id: {file, source_sha256, prepared, resource}}, {image id: 'compiled' | 'cache hit' | 'recompiled: source
    changed'}). Each is compiled from its PNG through compile_icon; the material names the image's own texture. The
    build status compares with the source SHA-256 this project last compiled for that image (build/.image-cache/
    index.json); record=True (the build) stores the new ones."""
    import hashlib
    from tools.hd2_archive import resource_hash
    from tools.hd2_image import image_name, icon_material, TEXTURE_TYPE, MATERIAL_TYPE
    project=Path(project)
    images=project_images(project)if images is None else images
    modes=image_preparations(spec,images)
    names={resource_hash(image_name(spec['resource'],i)):i for i in images}
    if len(names)!=len(images):raise ValueError('two image names share a resource hash; rename one image')
    index_path=project/'build'/IMAGE_CACHE/'index.json'
    try:index=json.loads(index_path.read_text(encoding='utf-8'))if index_path.is_file()else{}
    except ValueError:index={}
    if not isinstance(index,dict):index={}
    resources,sources,status={},{},{}
    for key,image_id in names.items():
        main,gpu,label,hit=compile_icon(project,images[image_id],modes[image_id])
        resources[(TEXTURE_TYPE,key)]=(main,gpu)
        resources[(MATERIAL_TYPE,key)]=(icon_material(key),b'')
        digest=hashlib.sha256(images[image_id]).hexdigest()
        sources[image_id]={'file':'images/'+image_id+'.png','source_sha256':digest,'prepared':label,
            'resource':image_name(spec['resource'],image_id)}
        previous=index.get(image_id)
        status[image_id]=('cache hit'if hit=='hit'and previous in(None,digest)else'compiled'if previous in(None,digest)
            else'recompiled: source changed')
        index[image_id]=digest
    if record:
        index_path.parent.mkdir(parents=True,exist_ok=True)
        index_path.write_text(json.dumps(dict(sorted(index.items())),indent=1)+'\n',encoding='utf-8')
    return resources,dict(sorted(sources.items())),status


IMAGE_RECORD='hd2runtime_images'


def image_record(sources,status):
    """The Lua resource <mod resource>/hd2runtime_images: each icon's source PNG, its SHA-256, how it was prepared and
    built, and its resource name. The Runtime logs it once per icon when the mod asks for it (runtime/image_resources)."""
    lines=['-- Generated by the HD2Runtime SDK build (docs/custom-images.md): the icons this mod compiled from its PNGs.',
        'return {format=1,images={']
    for image_id,item in sources.items():
        lines.append('['+json.dumps(image_id)+']={source='+json.dumps(item['file'])+',sha256='+json.dumps(item['source_sha256'])
            +',prepared='+json.dumps(item['prepared'])+',build='+json.dumps(status[image_id])+',resource='
            +json.dumps(item['resource'])+'},')
    lines.append('}}')
    return '\n'.join(lines)+'\n'


MODEL_CACHE='.model-cache'


def project_models_ids(project):
    folder=Path(project)/'models'
    return sorted(p.stem for p in folder.glob('*.json'))if folder.is_dir()else[]


def project_model_resources(project,spec):
    """The custom models of a project (docs/custom-models.md): ({base archive: {(type, name hash): parts}}, {model id:
    build record entry}, {model id: 'derived' | 'cache hit'}). Each models/<id>.json derives from its base weapon's unit
    in the installed game (tools/hd2_model.py; the base parts must be the reviewed ones, sdk/ModelBaseCapabilities.json),
    through the build's cache (build/.model-cache, keyed by the model file, the base facts and the mod's resource)."""
    import hashlib,pickle
    from tools.hd2_model import project_models,base_keys,derive,game_parts
    models=project_models(project)
    if not models:return {},{},{}
    bases=json.loads((SDK/'ModelBaseCapabilities.json').read_text(encoding='utf-8'))['bases']
    cache=Path(project)/'build'/MODEL_CACHE
    archives,records,status={},{},{}
    pending={}
    for model_id,m in models.items():
        base=bases.get(m['base'])
        if not base:
            raise ValueError('models/'+model_id+'.json: "base" must be a reviewed model base: '+', '.join(sorted(bases)))
        key=hashlib.sha256(json.dumps([spec['resource'],model_id,m,base],sort_keys=True).encode()).hexdigest()
        hit=cache/(key+'.bin')
        if hit.is_file():
            resources,record=pickle.loads(hit.read_bytes())
            status[model_id]='cache hit'
        else:
            pending[model_id]=(m,base,hit)
            continue
        archives.setdefault(base['archive'],{}).update(resources);records[model_id]=record
    if pending:
        keys=[]
        for m,base,_hit in pending.values():keys+=base_keys(base)
        parts=game_parts(sorted(set(keys)),os.environ.get('HD2_GAME_DATA'))
        for model_id,(m,base,hit) in pending.items():
            resources,record=derive(spec['resource'],model_id,m,base,parts)
            cache.mkdir(parents=True,exist_ok=True);hit.write_bytes(pickle.dumps((resources,record)))
            archives.setdefault(base['archive'],{}).update(resources);records[model_id]=record
            status[model_id]='derived'
    return archives,records,status


def build_project(project):
    from tools.hd2_archive import ARCHIVE_NAME, LUA_TYPE, make_archive, make_resource_archive, resource_hash, lua_resource
    project=Path(project).resolve();spec=json.loads((project/'hd2runtime.json').read_text())
    name=spec['resource'];required=spec['requires'];version=(project/'VERSION').read_text().strip()
    if not valid_resource(name):
        raise ValueError('Reserved or invalid resource identity')
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('VERSION must contain major.minor.patch')
    if spec.get('format')!=1:raise ValueError('Unsupported hd2runtime.json format')
    if required['bingus']!={'min_release':15,'api':1} or required['hd2runtime']['module']!=MODULE or required['hd2runtime']['api']!=1:
        raise ValueError('Unsupported dependency contract')
    minimum=required['hd2runtime']['min_version']
    if not re.fullmatch(SEMVER,minimum):raise ValueError('Invalid minimum runtime version (SemVer MAJOR.MINOR.PATCH)')
    optional=optional_dependencies(spec)
    # A custom stratagem project (docs/custom-stratagem-builder.md): custom_stratagems.json is validated and compiled
    # into src/addon.lua first (never over a hand-written one); the JSON ships beside the manifest, outside mod/.
    custom=None
    if (project/CUSTOM_STRATAGEMS).is_file():
        from tools.custom_stratagem_project import compile_project
        custom=compile_project(project,SDK)
        print('custom stratagems: '+', '.join(custom['ids'])+' compiled from '+CUSTOM_STRATAGEMS+' ('
            +custom['sha256'][:12]+(', src/addon.lua written)'if custom['written']else', src/addon.lua up to date)'))
    sources={}
    for path in sorted((project/'src').rglob('*.lua')):
        if path.is_symlink() or not path.resolve().is_relative_to(project/'src'):
            raise ValueError('Source must be inside project/src')
        relative=path.relative_to(project/'src').with_suffix('').as_posix()
        resource=name if relative=='addon' else name+'/'+relative
        body=path.read_text(encoding='utf-8-sig')
        if '---@meta' in body or '-- HD2-Addon:' in body:raise ValueError('SDK stubs or extra declarations are not gameplay source')
        if relative=='addon':body=wrap_addon(name,minimum,body,spec.get('name'))
        sources[resource]=body.encode()
    if name not in sources:raise ValueError('Missing src/addon.lua')
    images=project_images(project)
    # Custom models (docs/custom-models.md): each a patch of its base weapon's own package archive, beside the vanilla
    # resources; their build record a Lua resource of the mod (runtime/model_resources.lua reads it).
    from tools.hd2_model import RECORD as MODEL_RECORD,record_lua as model_record_lua
    model_archives,model_records,model_status=project_model_resources(project,spec)
    if model_records:
        if name+'/'+MODEL_RECORD in sources:raise ValueError('src/'+MODEL_RECORD+'.lua is reserved for the model record')
        sources[name+'/'+MODEL_RECORD]=model_record_lua(model_records).encode()
        print('models: '+', '.join(i+' '+model_status[i]+' (base '+r['base']+', archive '+r['archive']+')'
            for i,r in sorted(model_records.items())))
    gpu_resources=b''
    if images:
        # Lua and textures in the layout of the game's own archives; a Lua-only mod keeps make_archive's layout.
        resources={(LUA_TYPE,resource_hash(k)):(lua_resource(v),b'') for k,v in sources.items()}
        # Each image is a complete icon family under the mod's own name: its texture and its GUI material
        # (research/stratagem-icon-family-F5FEE03DCFDB.json), compiled from the editable PNG (masks prepared
        # automatically) through the build's source-hash cache. No atlas sprite; no vanilla resource is replaced.
        families,image_sources,image_status=project_icon_resources(project,spec,images,record=True)
        resources.update(families)
        # The build record of every icon, for the Runtime's load log; never a mod's own module name.
        if name+'/'+IMAGE_RECORD in sources:raise ValueError('src/'+IMAGE_RECORD+'.lua is reserved for the image record')
        record_name=name+'/'+IMAGE_RECORD
        resources[(LUA_TYPE,resource_hash(record_name))]=(lua_resource(image_record(image_sources,image_status).encode()),b'')
        for image_id,item in image_sources.items():item['build']=image_status[image_id]
        print('icons: '+', '.join(image_id+' '+image_status[image_id]+' ('+item['source_sha256'][:12]+')'
            for image_id,item in image_sources.items()))
        archive,gpu_resources=make_resource_archive(resources)
    else:
        archive=make_archive({resource_hash(k):lua_resource(v) for k,v in sources.items()})
    description='Requires Bingus Shared Loader v15+ / API 1 and HD2Runtime '+minimum+'+ / API 1; install dependencies separately.'
    if optional:description+=OPTIONS_NOTE
    manifest={'Version':1,'Guid':str(uuid.UUID(spec['guid'])),'Name':spec['name']+' '+version,'Description':description,
              'Options':[{'Name':spec['name'],'Description':description,'Include':['mod']}]}
    report={'resources':sorted(sources),'runtime_bundled':False,'sdk_stubs_bundled':False,
            'requires':required,'optional':optional,'deployed':False,'game_launched':False}
    if images:report['images']=sorted(images);report['image_sources']=image_sources
    if model_records:report['models']=model_records
    if custom:report['custom_stratagems']={k:custom[k] for k in ('source','sha256','addon','ids','images')}
    files={'manifest.json':json.dumps(manifest,indent=2).encode(),
           'hd2runtime.json':json.dumps({k:v for k,v in spec.items() if k not in ('sdk','ide_library')},indent=2).encode(),
           'build-report.json':json.dumps(report,indent=2).encode(),'README.md':(project/'README.md').read_bytes(),
           'mod/'+ARCHIVE_NAME:archive,'mod/'+ARCHIVE_NAME+'.stream':b'','mod/'+ARCHIVE_NAME+'.gpu_resources':gpu_resources}
    # The editable source of every image, beside the manifest: outside the installed option folder (mod/), so the
    # game never reads it; the archive holds what was compiled from it.
    for image_id,png in images.items():files['images/'+image_id+'.png']=png
    # Each model base archive: a patch of that package archive (the mod manager numbers patches; never a vanilla name).
    for archive_name,resources in sorted(model_archives.items()):
        if archive_name+'.patch_0'==ARCHIVE_NAME:raise ValueError('a model never patches the boot archive')
        patch,patch_gpu=make_resource_archive(resources)
        files['mod/'+archive_name+'.patch_0']=patch
        files['mod/'+archive_name+'.patch_0.stream']=b''
        files['mod/'+archive_name+'.patch_0.gpu_resources']=patch_gpu
    for model_id in project_models_ids(project):files['models/'+model_id+'.json']=(project/'models'/(model_id+'.json')).read_bytes()
    if custom:files[CUSTOM_STRATAGEMS]=(project/CUSTOM_STRATAGEMS).read_bytes()
    path=project/'build'/(project.name+'-'+version+'.zip');zip_files(path,files)
    # The same report beside the ZIP, with the artifact's name and digest: what a builder reads after a rebuild.
    import hashlib
    (project/'build'/'build-report.json').write_text(json.dumps(dict(report,artifact=path.name,version=version,
        artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),indent=2)+'\n',encoding='utf-8')
    return path


def custom_stratagem_command(action,target):
    """hd2.py custom-stratagem validate <project or JSON> | compile <project>: 0 when valid (and compiled)."""
    from tools.custom_stratagem_project import compile_project, load_schema, validate
    target=Path(target)
    if target.is_dir() and not (target/CUSTOM_STRATAGEMS).is_file():
        raise ValueError(str(target)+' has no '+CUSTOM_STRATAGEMS+' (a hand-written src/addon.lua needs no compile)')
    if action=='compile':
        result=compile_project(target,SDK)
        return 'compiled '+', '.join(result['ids'])+' into '+result['addon']+(''if result['written']else' (up to date)')
    path=target/CUSTOM_STRATAGEMS if target.is_dir() else target
    problems=validate(json.loads(path.read_text(encoding='utf-8-sig')),load_schema(SDK))
    if problems:raise ValueError(str(path)+' is not valid:\n  '+'\n  '.join(problems))
    return str(path)+' is valid'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('inspect');p.add_argument('kind',choices=['weapon','vehicle','stratagem','equipment','type']);p.add_argument('name');p.add_argument('--json',action='store_true')
    p=sub.add_parser('new');p.add_argument('path',type=Path);p.add_argument('--name',required=True);p.add_argument('--template',choices=['fire_rate','projectile_damage'],default='fire_rate');p.add_argument('--sdk',type=Path,default=SDK)
    p=sub.add_parser('configure');p.add_argument('project',type=Path);p.add_argument('--sdk',type=Path,default=SDK)
    p=sub.add_parser('build');p.add_argument('project',type=Path)
    p=sub.add_parser('custom-stratagem',help='validate or compile a custom_stratagems.json project')
    p.add_argument('action',choices=['validate','compile']);p.add_argument('project',type=Path)
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
    # In-mission capture through the armed capture package (docs/snapshots.md#armed-in-mission-capture).
    def delay_type(text):
        from tools.snapshot_control import parse_delay
        try:return parse_delay(text)
        except ValueError as error:raise argparse.ArgumentTypeError(str(error))
    def label_type(text):
        from tools.snapshot_control import sanitize_label
        try:return sanitize_label(text)
        except ValueError as error:raise argparse.ArgumentTypeError(str(error))
    arm=snapshot_sub.add_parser('arm',help='capture a snapshot from the running game: now, after a delay, or on ENTER')
    when=arm.add_mutually_exclusive_group()
    when.add_argument('--delay',type=delay_type,metavar='SECONDS',help='wait this many seconds, then capture')
    when.add_argument('--wait-for-key',action='store_true',help='capture when ENTER is pressed in this window')
    arm.add_argument('--label',type=label_type,help='name suffix for the snapshot file (letters, digits, . _ -)')
    arm.add_argument('--repeat',action='store_true',help='with --wait-for-key: stay armed after each capture (q quits)')
    arm.add_argument('--control-dir',type=Path,help='control folder (default: the snapshot folder\\control)')
    arm.add_argument('--ack-timeout',type=float,default=60.0,metavar='SECONDS',
        help='how long the game may take to accept the request (default 60)')
    status_parser=snapshot_sub.add_parser('status',help='show what the armed capture package last reported')
    status_parser.add_argument('--control-dir',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='inspect':
            result=inspect(args.kind,args.name);print(json.dumps(result,indent=2) if args.json else format_inspection(result))
        elif args.command=='new':print(new_project(args.path,args.name,args.template,args.sdk))
        elif args.command=='configure':configure(args.project,args.sdk);print('IDE configuration updated')
        elif args.command=='build':print(build_project(args.project))
        elif args.command=='custom-stratagem':print(custom_stratagem_command(args.action,args.project))
        elif args.snapshot_command=='scan-weapons':
            from tools.snapshot_scan import scan
            output,mapping=scan(args.snapshot,args.wiki,args.output,args.historical_analysis,args.lua_dll)
            print(output);print(mapping)
        elif args.snapshot_command=='arm':
            from tools.snapshot_control import Options,arm as arm_snapshot
            if args.repeat and not args.wait_for_key:parser.error('--repeat needs --wait-for-key')
            mode='manual'if args.wait_for_key else'delay'if args.delay is not None else'immediate'
            try:
                arm_snapshot(Options(mode=mode,delay=args.delay or 0.0,label=args.label,repeat=args.repeat,
                    directory=args.control_dir,ack_timeout=args.ack_timeout))
            except KeyboardInterrupt:parser.exit(130,'cancelled\n')
        elif args.snapshot_command=='status':
            from tools.snapshot_control import status
            print(status(args.control_dir))
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
