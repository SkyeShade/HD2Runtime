"""Validate the built runtime ZIP itself, the way HD2 loads it.

Source-tree tests preload every module, which hides packaging and load-order faults.
This validator reads only the shipped archive:

1. Static: every internal module name referenced by shipped Lua, and every name in
   the generated package module list, resolves to a resource in the archive.
2. Dynamic: the archive runs on HD2's own lua51.dll behind an emulated Bingus
   loader. As in game, archived resources resolve through package.loaders only
   during startup; afterwards lookups fail with "module not found". Real addons
   then apply through the packaged API against the retained snapshot, using a
   copy-on-write memory overlay (no game process, no real writes), and each ensure
   must re-apply after a simulated reset.

Only runtime/windows_write is substituted, so writes land in the overlay.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hd2_archive import resource_hash

SNAPSHOT = Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')
ENTRY = 'mods/skyeshade/hd2runtime'
PACKAGE_MODULES = 'hd2runtime/runtime/package_modules'
WRITE_ADAPTER = 'hd2runtime/runtime/windows_write'
REFERENCE = re.compile(rb"""['"](hd2runtime/[A-Za-z0-9_/]+)['"]""")

GUI_TRANSACTION = r'''local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-957b6b7e6b9132eff9fbc6fb',
        target=hd2.weapon('AR-23C Liberator Concussive'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.ap_direct,expect=2,value=3},
            {field=hd2.fields.damage.ap_extreme,expect=2,value=3},
            {field=hd2.fields.damage.ap_large,expect=2,value=3},
            {field=hd2.fields.damage.ap_slight,expect=2,value=3},
            {field=hd2.fields.damage.push_force,expect=60,value=30},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    patch={
        id='gui-object-b52a010dda6a8e42722ba35c',
        target=hd2.weapon('AR-23C Liberator Concussive'),
        field=hd2.fields.weapon.fire_rate,
        expect=400,
        value=1100,
    }
})
return operations
'''
SIMPLE_PATCH = r'''local hd2=require('mods/skyeshade/hd2runtime')
return hd2.patch({id='concussive-fire-rate',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=1100})
'''


SUPPORT_COVERAGE = r'''local hd2=require('mods/skyeshade/hd2runtime')
local mg43=hd2.support_weapon('MG-43 Machine Gun')
local operations={}
-- Delivery-resolved identity (call-in rack chain re-proven live) plus a reload duration.
operations[#operations+1]=hd2.ensure({plan={id='mg43-coverage',operations={
    {id='rate',target=mg43,field=hd2.fields.weapon.fire_rate,expect=760,value=900},
    {id='reload',target=mg43,allow_unverified_effect=true,
        field=hd2.fields.reload.duration,expect=4.5,value=3},
}}})
operations[#operations+1]=hd2.ensure({patch={id='maxigun-windup',target=hd2.support_weapon('M-1000 Maxigun'),
    field=hd2.fields.windup.wind_up_seconds,expect=0.5,value=0.2}})
operations[#operations+1]=hd2.ensure({patch={id='rl77-lifetime',allow_shared=true,
    target=hd2.support_weapon('RL-77 Airburst Rocket Launcher'):attack('primary'):projectile(),
    field=hd2.fields.projectile.lifetime,expect=1.5,value=3}})
return operations
'''


def example(name):
    return (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text()


SCENARIOS = {
    'player-weapon-patch': lambda: SIMPLE_PATCH,
    'player-weapon-transaction-gui': lambda: GUI_TRANSACTION,
    'support-weapon': lambda: example('SupportAMRProof'),
    'support-weapon-coverage': lambda: SUPPORT_COVERAGE,
    'stratagem': lambda: example('SupportStratagemCooldownProof'),
    'vehicle-armor': lambda: example('BastionReArmoredRecreation'),
    'vehicle-mount': lambda: example('FRVWeaponSwapRecreation'),
    'backpack': lambda: example('JumpPackRecreation'),
    'shield-relay': lambda: example('ShieldRelayRecreation'),
    'magazine-attachment': lambda: example('ConcussiveDrumMagazine'),
    'booster-deployed-entity': lambda: example('ArmedResupplyTurret'),
    'booster-status-effect': lambda: example('CombatStimBoost'),
}


def archive_resources(path):
    """Map resource-name hash to Lua source for the runtime archive inside a ZIP."""
    with zipfile.ZipFile(path) as package:
        data = package.read(next(name for name in package.namelist() if name.endswith('.patch_0')))
    count = struct.unpack_from('<I', data, 8)[0]
    found = {}
    for index in range(count):
        row = struct.unpack_from('<7Q6I', data, 104 + index * 80)
        length, version = struct.unpack_from('<II', data, row[2])
        assert version == 2, 'unexpected Lua resource version'
        found[row[0]] = data[row[2] + 8:row[2] + 8 + length]
    return found


def static_scan(resources):
    """Resolve every referenced internal module name against the archive by hash."""
    if resource_hash(ENTRY) not in resources:
        raise AssertionError('runtime entry resource is missing: ' + ENTRY)
    references = {}
    for body in resources.values():
        for match in REFERENCE.finditer(body):
            references.setdefault(match.group(1).decode(), 0)
            references[match.group(1).decode()] += 1
    listed = []
    modules = resources.get(resource_hash(PACKAGE_MODULES))
    if modules is not None:
        listed = [match.group(1).decode() for match in REFERENCE.finditer(modules)]
    names = sorted(set(references) | set(listed))
    unresolved = [name for name in names if resource_hash(name) not in resources]
    known = {resource_hash(name) for name in names} | {resource_hash(ENTRY)}
    return {'resources': len(resources), 'referencedModules': len(references),
        'packageModuleList': bool(modules), 'listedModules': len(listed),
        'unresolved': unresolved, 'unnamedResources': len(set(resources) - known),
        'names': names}


def lua_bytes(data: bytes) -> str:
    """A Lua 5.1 string literal for arbitrary bytes."""
    out = []
    for byte in data:
        if 32 <= byte < 127 and byte not in (34, 92):
            out.append(chr(byte))
        else:
            out.append('\\%03d' % byte)
    return '"' + ''.join(out) + '"'


def lua(value): return lua_bytes(str(value).encode())


def harness_sources():
    """Offline infrastructure loaded privately, never into the artifact's package tables."""
    names = ['hd2runtime/core/binary', 'hd2runtime/core/snapshot_format',
        'hd2runtime/runtime/snapshot_memory_reader', 'hd2runtime/primary_mapper/json']
    return {name: (ROOT / (name.split('/', 1)[1] + '.lua')).read_bytes() for name in names}


PROGRAM = r'''
-- Private harness modules: own cache and require, so they never populate package.loaded.
local private_loaded={}
local function private_require(name)
 if private_loaded[name]~=nil then return private_loaded[name]end
 if name=='ffi' or name=='bit' then return require(name)end
 local chunk=assert(loadstring(assert(HARNESS[name],'harness module missing: '..name),'@harness/'..name))
 setfenv(chunk,setmetatable({require=private_require},{__index=_G}))
 local value=chunk(name);if value==nil then value=true end
 private_loaded[name]=value;return value
end
local json=private_require('hd2runtime/primary_mapper/json')
local source=private_require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=EXE_SHA,expected_dll_sha=DLL_SHA})

-- Copy-on-write overlay adapter handed to the packaged API as windows_write.create().
local PAGE=4096
local overlay,protection,simulated={}, {},0
local counts={writes=0,protection_changes=0,module_hashes=0}
local runtime={mode='live-overlay'}
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)counts.module_hashes=counts.module_hashes+1;return source.module_hash(handle)end
function runtime.monotonic_time()return simulated end
function runtime.query(at)
 local r,why=source.query(at)
 if not r or r.allocation_base==0 then return r,why end
 local low,high=r.base,r.base+r.size
 local pages={}
 for page in pairs(protection)do if page>=low and page<high then pages[#pages+1]=page end end
 if #pages==0 then return r end
 table.sort(pages)
 for _,page in ipairs(pages)do
  if at>=page and at<page+PAGE then r.base=page;r.size=PAGE;r.protect=protection[page];return r end
  if page>at then high=math.min(high,page)else low=math.max(low,page+PAGE)end
 end
 r.base=low;r.size=high-low;return r
end
function runtime.read(at,n)
 local bytes,why=source.read(at,n)
 if not bytes then return nil,why end
 for address,value in pairs(overlay)do
  if address<at+n and address+#value>at then
   local first=math.max(address,at);local last=math.min(address+#value,at+n)
   bytes=bytes:sub(1,first-at)..value:sub(first-address+1,last-address)..bytes:sub(last-at+1)
  end
 end
 return bytes
end
function runtime.protect(page,size,value)
 assert(page%PAGE==0 and size==PAGE,'overlay protect extent')
 counts.protection_changes=counts.protection_changes+1
 local old=protection[page] or original_protect(page)
 if value==original_protect(page)then protection[page]=nil else protection[page]=value end
 return old
end
function runtime.write(at,bytes)
 assert((protection[at-at%PAGE] or original_protect(at-at%PAGE))==4,'overlay write without writable page')
 counts.writes=counts.writes+1;overlay[at]=bytes
 return true,nil,#bytes
end

-- Emulated engine resource lookup: archive resources resolve only during startup.
local startup_open=true
local lookups={startup=0,late_found=0,late_missing={}}
local adapter_module='return {create=function()return rawget(_G,"HD2RuntimeArtifactOverlay")end}'
rawset(_G,'HD2RuntimeArtifactOverlay',runtime)
local function engine_searcher(name)
 local body=RESOURCES[name]
 if name==WRITE_ADAPTER and body then body=adapter_module end
 if not body then return '\n\tno resource '..name end
 if not startup_open then
  lookups.late_missing[#lookups.late_missing+1]=name
  return '\n\tno resource '..name..' (startup package unloaded)'
 end
 lookups.startup=lookups.startup+1
 return assert(loadstring(body,'@'..name..'.lua'))
end
for name in pairs(package.preload)do package.preload[name]=nil end
local preload_searcher=package.loaders[1]
for index=#package.loaders,1,-1 do package.loaders[index]=nil end
package.loaders[1]=preload_searcher;package.loaders[2]=engine_searcher

local lines={}
rawset(_G,'CowboyBingusModLoader',{api=1,version=16,modules={},
 open_log=function()return {write=function(_,text)lines[#lines+1]=text end,flush=function()end}end})
rawset(_G,'update',nil)

-- Startup: Bingus requires the runtime entry, then the gameplay addon.
local watches={}
local ok,why=pcall(require,ENTRY)
if not ok then return json.encode({startup_error=tostring(why),log=lines})end
local chunk=assert(loadstring(ADDON,'@'..SCENARIO..'/addon.lua'))
local ok_addon,returned=pcall(chunk)
if not ok_addon then return json.encode({startup_error=tostring(returned),log=lines})end
if type(returned)=='table' and returned.status==nil then
 for _,watch in ipairs(returned)do watches[#watches+1]=watch end
else watches[#watches+1]=returned end
startup_open=false

local FRAME=0.1
local function frame()simulated=simulated+FRAME;if update then update(FRAME)end end
local function done(watch)
 if watch.runs~=nil then return watch.status=='rejected' or (watch.runs>=1 and watch.status=='waiting')end
 return watch.status=='complete' or watch.status=='rejected' or watch.status=='cancelled'
end
local function settled()for _,w in ipairs(watches)do if not done(w)then return false end end;return true end
local frames=0
while not settled()and frames<36000 do frame();frames=frames+1 end
local function describe()
 local out={}
 for _,w in ipairs(watches)do
  out[#out+1]={id=w.id,kind=w.runs~=nil and 'ensure' or 'once',status=w.status,runs=w.runs,
   error=w.error,result=w.result and w.result.status,code=w.result and w.result.code,
   writes=w.result and w.result.writes}
 end
 return out
end
local report={scenario=SCENARIO,settled=settled(),startup_seconds=simulated,watches=describe(),
 counts={writes=counts.writes,protection_changes=counts.protection_changes,module_hashes=counts.module_hashes}}

-- Simulated game reset: ensures must detect drift and re-apply with lookups still closed.
local ensures={}
for index,w in ipairs(watches)do if w.runs~=nil and w.status~='rejected' then ensures[index]=w.runs end end
if next(ensures)then
 overlay={};protection={}
 local seconds=0
 local function reapplied()
  for index,runs in pairs(ensures)do
   local w=watches[index]
   if w.status=='rejected' or w.runs<=runs then return false end
  end
  return true
 end
 while not reapplied()and seconds<3600 do frame();seconds=seconds+FRAME end
 report.reset={reapplied=reapplied(),seconds=seconds,watches=describe()}
end
report.lookups={startup=lookups.startup,late_missing=lookups.late_missing}
report.log=lines
source.close()
return json.encode(report)
'''


def run_scenario(resources, names, scenario, addon, snapshot):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    profile = resources[resource_hash('hd2runtime/schemas/current')].decode('latin-1')
    exe_sha = re.search(r'"exe_sha"\]="([0-9A-Fa-f]{64})"', profile).group(1)
    dll_sha = re.search(r'"dll_sha"\]="([0-9A-Fa-f]{64})"', profile).group(1)
    table = {name: resources[resource_hash(name)] for name in names + [ENTRY] if resource_hash(name) in resources}
    program = ('local RESOURCES={' + ','.join('[' + lua(k) + ']=' + lua_bytes(v) for k, v in table.items()) + '}\n'
        + 'local HARNESS={' + ','.join('[' + lua(k) + ']=' + lua_bytes(v) for k, v in harness_sources().items()) + '}\n'
        + 'local SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal EXE_SHA=' + lua(exe_sha)
        + '\nlocal DLL_SHA=' + lua(dll_sha) + '\nlocal ENTRY=' + lua(ENTRY) + '\nlocal WRITE_ADAPTER=' + lua(WRITE_ADAPTER)
        + '\nlocal SCENARIO=' + lua(scenario) + '\nlocal ADDON=' + lua(addon) + '\n' + PROGRAM)
    return json.loads(execute(program.encode()))


def check(report):
    """Return the failures for one scenario report."""
    failures = []
    if 'startup_error' in report:
        return ['startup: ' + report['startup_error']]
    if report.get('lookups', {}).get('late_missing'):
        failures.append('modules required after startup: ' + ', '.join(sorted(set(report['lookups']['late_missing']))))
    if not report.get('settled'):
        failures.append('did not settle')
    for watch in report.get('watches', []):
        if watch.get('result') != 'APPLIED' or watch.get('status') == 'rejected':
            failures.append('%s: status=%s result=%s error=%s' % (watch.get('id'), watch.get('status'),
                watch.get('result'), watch.get('error')))
    reset = report.get('reset')
    if reset is not None and not reset['reapplied']:
        failures.append('ensure did not re-apply after reset')
    if any('not found' in line for line in report.get('log', [])):
        failures.append('log reports a missing module')
    return failures


def validate(zip_path, snapshot=SNAPSHOT, scenarios=None):
    """Validate a built runtime ZIP; raise AssertionError with details on any failure."""
    resources = archive_resources(zip_path)
    scan = static_scan(resources)
    result = {'artifact': Path(zip_path).name, 'static': {k: v for k, v in scan.items() if k != 'names'},
        'scenarios': {}, 'gameProcessAccess': False, 'realWrites': 0}
    failures = ['unresolved module: ' + name for name in scan['unresolved']]
    if not scan['packageModuleList']:
        failures.append('package module list is missing: ' + PACKAGE_MODULES)
    for name in scenarios or SCENARIOS:
        report = run_scenario(resources, scan['names'], name, SCENARIOS[name](), snapshot)
        problems = check(report)
        result['scenarios'][name] = {'passed': not problems, 'problems': problems,
            'watches': report.get('watches'), 'reset': report.get('reset', {}).get('reapplied'),
            'overlayWrites': report.get('counts', {}).get('writes'),
            'moduleHashes': report.get('counts', {}).get('module_hashes'),
            'lateLookupsMissing': sorted(set(report.get('lookups', {}).get('late_missing', [])))}
        failures += [name + ': ' + problem for problem in problems]
    result['passed'] = not failures
    if failures:
        raise AssertionError('packaged runtime validation failed:\n' + '\n'.join(failures)
            + '\n' + json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path, help='built HD2Runtime-<version>-runtime.zip')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--scenario', action='append', choices=sorted(SCENARIOS))
    parser.add_argument('--output', type=Path, help='write the JSON report here')
    args = parser.parse_args()
    try:
        result = validate(args.zip, args.snapshot, args.scenario)
    except AssertionError as error:
        print(error)
        raise SystemExit(1)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    for name, item in result['scenarios'].items():
        print(name, 'PASS' if item['passed'] else 'FAIL', 'writes=%s' % item['overlayWrites'],
            'reset_reapplied=%s' % item['reset'])


if __name__ == '__main__':
    main()
