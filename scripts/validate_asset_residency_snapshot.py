"""Validate automatic asset loading offline: the production residency reader and loader proofs against every
retained snapshot, plus the scheduler gate's state machine with a simulated engine loader.

Real snapshot memory (no game process, nothing written, no native call):
* core/assets.prove re-proves the build, the exact code bytes of game.dll's RefcountedPackageSystem request and
  release functions and of the engine's has_loaded / package lookup, and the reference-map instance;
* core/assets.state reads the engine's package list and part states: each snapshot's equipped loadout packages
  are 'resident', the armory preview captured mid-load (155654Z marksman_rifle) is not resident yet, and an
  item nobody carries (EAT-700) is 'absent';
* tampered code bytes, a different build and an unknown package are rejected.

Simulated engine loader (same production gate the packaged runtime uses): request-once deduplication across
operations, waiting -> ready, bounded timeout -> ASSET_UNAVAILABLE, a runtime without native package loading
-> ASSET_UNAVAILABLE, the session package budget, and an unmodified spec with no dependency passing straight
through.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from validate_entity_authoring_snapshot import lua, sources  # noqa: E402

OUTPUT = ROOT / 'validation/asset-residency-snapshot.json'
CASES = {
    'F5FEE03DCFDB-20260926T222226Z.hd2snap': {'resident': ['0x10A7605527187EF5'], 'notResident': []},
    'F5FEE03DCFDB-20260927T155654Z.hd2snap': {'resident': ['0xDBD9381F9EA9788F'],
        'notResident': ['0x9974F498C67D5E20']},
    'F5FEE03DCFDB-20260927T160033Z.hd2snap': {'resident': ['0xDBD9381F9EA9788F'], 'notResident': []},
}
ABSENT = '0x5D68E55823ACD1BF'      # packages/generated/loadout/expendable_napalm_launcher (EAT-700)

PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local assets=require('hd2runtime/core/assets')
local database=require('hd2runtime/domains/package_residency')
local fingerprint=require('hd2runtime/core/fingerprint')
local json=require('hd2runtime/primary_mapper/json')
local result={snapshot=SNAPSHOT_NAME,states={},rejections={}}
local function rejects(fn,needle,label)
 local ok,why=pcall(fn)
 assert(not ok,label..' was not rejected')
 assert(tostring(why):find(needle,1,true),label..' rejected for the wrong reason: '..tostring(why))
 result.rejections[#result.rejections+1]=label
end
-- Overlay runtime over the snapshot so tamper cases never touch the source.
local overlay,tamper={},{}
local runtime={mode='snapshot-overlay'}
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.module_hash(handle)if tamper.hash then return tamper.hash end;return source.module_hash(handle)end
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
local function reset()overlay={};tamper={};assets.reset();fingerprint.reset()end

-- 1. proofs and residency on real memory
local pins=assets.prove(runtime)
result.proven=pins.instance~=0 and pins.capacity>0
for _,id in ipairs(RESIDENT)do
 local state=assets.state(runtime,id);result.states[id]=state
 assert(state=='resident','equipped loadout package is not resident: '..id..' '..state)
end
for _,id in ipairs(NOT_RESIDENT)do
 local state=assets.state(runtime,id);result.states[id]=state
 assert(state~='resident','package captured mid-load reads resident: '..id)
end
local absent=assets.state(runtime,ABSENT);result.states[ABSENT]=absent
assert(absent=='absent','uncarried EAT-700 package is not absent: '..absent)
-- 2. tamper rejections (fresh proofs each time)
local dll=source.module('game.dll')
reset()
overlay[dll+database.loader.requestRva+5]=string.char((source.read(dll+database.loader.requestRva+5,1):byte()+1)%256)
rejects(function()assets.prove(runtime)end,'native package loader changed','changed request code byte')
reset()
local exe=source.module(nil)
overlay[exe+database.loader.engine.hasLoadedRva+9]='\255'
rejects(function()assets.prove(runtime)end,'native package loader changed','changed engine has_loaded byte')
reset()
tamper.hash=string.rep('0',64)
rejects(function()assets.prove(runtime)end,'unsupported build fingerprint','wrong build')
reset()
rejects(function()assets.request(runtime,{package='0x1234567890ABCDEF',label='forged'},'x')end,
 'not in the catalog','uncatalogued package')
rejects(function()assets.request(runtime,assets.dependency('support_weapon/EAT-700 Expendable Napalm'),'x')end,
 'cannot request packages','runtime without native package loading')
-- 3. gate state machine with a simulated loader
reset()
local calls,loaded,clock={}, {},0
runtime.package_request=function(entry,instance,id)
 assert(entry==source.module('game.dll')+database.loader.requestRva,'native request entry is not the proven function')
 assert(instance==pins.instance,'native request instance is not the proven system')
 calls[#calls+1]=id;return true
end
runtime.package_state=function(hex)return loaded[hex]and'resident'or'queued'end
local dependency=assets.dependency('support_weapon/EAT-700 Expendable Napalm')
local spec_a={id='op-a',asset_dependencies={dependency}}
local spec_b={id='op-b',asset_dependencies={dependency}}
local gate_a,gate_b=assets.gate(runtime,spec_a),assets.gate(runtime,spec_b)
assert(gate_a.tick(0.3)=='waiting'and gate_b.tick(0.3)=='waiting','gates must wait for the load')
assert(#calls==1,'one package requested by two operations must be requested natively once')
loaded[dependency.package]=true
assert(gate_a.tick(0.3)=='ready'and gate_b.tick(0.3)=='ready','gates must open once resident')
result.dedupedNativeRequests=#calls
local held=assets.holdings();assert(#held==1 and #held[1].holders==2,'both operations hold the package')
assets.release('op-a');held=assets.holdings();assert(#held[1].holders==1 and held[1].retained,'release is bookkeeping only')
-- timeout
reset();calls={};loaded={}
local gate=assets.gate(runtime,{id='op-t',asset_dependencies={dependency}})
local state,why
for _=1,2000 do state,why=gate.tick(0.1);if state~='waiting'then break end end
assert(state=='failed'and tostring(why):find('ASSET_UNAVAILABLE',1,true)and tostring(why):find('expendable_napalm_launcher',1,true),
 'timeout must fail with ASSET_UNAVAILABLE naming the package: '..tostring(why))
result.timeoutReason=why
-- no dependency: ready immediately, no native call
reset();calls={}
assert(assets.gate(runtime,{id='op-n'}).tick(0)=='ready'and #calls==0,'specs without dependencies pass through')
-- budget
reset();calls={}
local keys={};for key in pairs(database.dependencies)do keys[#keys+1]=key end;table.sort(keys)
local distinct,seen={}, {}
for _,key in ipairs(keys)do
 local item=database.dependencies[key]
 if not seen[item.package]then seen[item.package]=true;distinct[#distinct+1]=key end
end
for index=1,database.policy.maxHeldPackages do assets.request(runtime,assets.dependency(distinct[index]),'budget')end
rejects(function()assets.request(runtime,assets.dependency(distinct[database.policy.maxHeldPackages+1]),'budget')end,
 'package budget','session package budget')
result.budget=database.policy.maxHeldPackages
source.close()
result.status='VALIDATED'
return json.encode(result)
'''


def validate():
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
    results = []
    for name, case in CASES.items():
        path = build_profile.snapshot_directory() / name
        program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(path.resolve()) + '\nlocal SNAPSHOT_NAME=' + lua(name)
            + '\nlocal RESIDENT={' + ','.join(lua(v) for v in case['resident']) + '}'
            + '\nlocal NOT_RESIDENT={' + ','.join(lua(v) for v in case['notResident']) + '}'
            + '\nlocal ABSENT=' + lua(ABSENT) + '\n' + PROGRAM)
        results.append(json.loads(execute(program.encode())))
    return {'status': 'VALIDATED' if all(r['status'] == 'VALIDATED' for r in results) else 'FAILED',
        'snapshots': results, 'writes': 0, 'nativeCalls': 0, 'mode': 'snapshot'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
