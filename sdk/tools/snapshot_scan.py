"""Execute the production Lua weapon mapper against an HD2SNAP file."""
from __future__ import annotations

from pathlib import Path
import json

from .lua_runner import execute
from .wiki_primary import compact

SDK=Path(__file__).resolve().parents[1]
ROOT=SDK.parent
MODULE_PATHS={
    'hd2runtime/core/binary':'core/binary.lua','hd2runtime/core/bytes':'core/bytes.lua',
    'hd2runtime/core/entity_catalog':'core/entity_catalog.lua','hd2runtime/core/settings':'core/settings.lua',
    'hd2runtime/core/snapshot_format':'core/snapshot_format.lua','hd2runtime/runtime/reader':'runtime/reader.lua',
    'hd2runtime/runtime/discover':'runtime/discover.lua','hd2runtime/runtime/snapshot_memory_reader':'runtime/snapshot_memory_reader.lua',
    'hd2runtime/schemas/current':'schemas/current.lua','hd2runtime/schemas/weapon_mapper':'schemas/weapon_mapper.lua',
    'hd2runtime/api/weapon_mapper':'api/weapon_mapper.lua',
    'hd2runtime/primary_mapper/matcher':'primary_mapper/matcher.lua','hd2runtime/primary_mapper/json':'primary_mapper/json.lua',
    'hd2runtime/primary_mapper/report':'primary_mapper/report.lua'}


def lua(value):
    if isinstance(value,dict):return '{'+','.join('['+lua(k)+']='+lua(v) for k,v in value.items())+'}'
    if isinstance(value,(list,tuple)):return '{'+','.join(lua(v) for v in value)+'}'
    if isinstance(value,bool):return'true'if value else'false'
    if value is None:return'nil'
    if isinstance(value,(int,float)):return repr(value)
    return json.dumps(str(value),ensure_ascii=True)


def module_sources():
    bundle=SDK/'tools/snapshot_scan_modules.json'
    if bundle.is_file():return json.loads(bundle.read_text())
    if not (ROOT/'core/snapshot_format.lua').is_file():
        raise ValueError('Snapshot scanner module bundle is absent from this SDK')
    return {name:(ROOT/path).read_text() for name,path in MODULE_PATHS.items()}


def bundle_bytes():
    return (json.dumps({name:(ROOT/path).read_text() for name,path in MODULE_PATHS.items()},
        sort_keys=True,separators=(',',':'))+'\n').encode()


def scan(snapshot: Path,wiki: Path,output: Path|None=None,historical=False,lua_dll: Path|None=None):
    snapshot=Path(snapshot).resolve();wiki=Path(wiki).resolve()
    if not snapshot.is_file():raise ValueError('Snapshot file not found: '+str(snapshot))
    dataset=compact(wiki)
    if dataset['weapon_count']!=55:raise ValueError('Expected 55 primary weapons in wiki dataset')
    sdk_metadata=json.loads((SDK/'metadata.json').read_text())
    runtime_version=sdk_metadata['runtime_version']
    sources=module_sources()
    preload='\n'.join('package.preload['+lua(name)+']=function(...) return assert(loadstring('
        +lua(body)+','+lua(name)+'))(...) end' for name,body in sources.items())
    program=preload+'''\nlocal profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open('''+lua(str(snapshot))+''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha,historical_analysis='''+lua(historical)+'''})
local job=require('hd2runtime/api/weapon_mapper').start(source,function()end,{historical_analysis='''+lua(historical)+'''})
for _=1,200000 do if job.step()then break end end
assert(job.status=='complete',job.error or 'snapshot scan did not complete')
local full,mapping=require('hd2runtime/primary_mapper/report').compose(job.result,'''+lua(dataset)+''',
 {version='''+lua(runtime_version)+''',commit='offline-snapshot'})
source.close()
return require('hd2runtime/primary_mapper/json').encode({report=full,weaponIdentityCandidates=mapping})
'''
    decoded=json.loads(execute(program.encode(),lua_dll))
    output=Path(output)if output else snapshot.with_suffix('.weapon-map.json')
    output.write_text(json.dumps(decoded['report'],indent=2)+'\n')
    mapping=output.with_name(output.stem+'.identity-candidates.json')
    mapping.write_text(json.dumps(decoded['weaponIdentityCandidates'],indent=2)+'\n')
    return output,mapping
