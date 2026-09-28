"""Steady-state runtime cost audit for ensured Runtime mods, on real native data.

The retained current-build snapshot is wrapped in a copy-on-write overlay that adds
simulated WriteProcessMemory/VirtualProtect, so hd2.ensure runs the production
discovery, resolution, transaction, and verification code end to end without a
game process. Every adapter call is counted (VirtualQuery, reads, bytes, module
hashes, protection changes, writes), which also allows the same scenarios to be
replayed against an older source tree for a before/after comparison.

Scenarios: each example mod alone (startup, then a steady-state window, then a
simulated game reinitialization of its targets), plus all mods together.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)
SNAPSHOT = build_profile.SNAPSHOT
OUTPUT = ROOT / 'validation/steady-state-audit.json'
GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2')
EXAMPLES = ['ShieldRelayRecreation', 'BastionReArmoredRecreation', 'FRVWeaponSwapRecreation',
    'JumpPackRecreation', 'SupportAMRProof', 'AntiTankEmplacementProof', 'ConcussiveDrumMagazine']


def lua(value): return json.dumps(str(value), ensure_ascii=False)


def sources(root):
    result = {}
    for folder in ('api', 'core', 'runtime', 'schemas', 'domains', 'primary_mapper'):
        for path in sorted((root / folder).glob('*.lua')):
            result['hd2runtime/' + path.relative_to(root).with_suffix('').as_posix()] = path.read_text()
    return result


PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local json=require('hd2runtime/primary_mapper/json')
local has_metrics=pcall(require,'hd2runtime/runtime/metrics')
local metrics=has_metrics and require('hd2runtime/runtime/metrics') or nil
if metrics then metrics.set_clock(os.clock)end
local PAGE=4096
local counts
local function reset_counts()
 counts={queries=0,reads=0,read_bytes=0,module_hashes=0,writes=0,write_bytes=0,
  identical_writes=0,protection_changes=0,log_lines=0}
end
reset_counts()
local overlay,protection={},{}
local runtime={mode='live-overlay'}
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)counts.module_hashes=counts.module_hashes+1;return source.module_hash(handle)end
function runtime.query(at)
 counts.queries=counts.queries+1
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
 counts.reads=counts.reads+1;counts.read_bytes=counts.read_bytes+n
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
 local page=at-at%PAGE
 assert((protection[page] or original_protect(page))==4,'overlay write without writable page')
 if runtime.read(at,#bytes)==bytes then counts.identical_writes=counts.identical_writes+1 end
 counts.writes=counts.writes+1;counts.write_bytes=counts.write_bytes+#bytes
 overlay[at]=bytes
 return true,nil,#bytes
end
local simulated=0
function runtime.monotonic_time()return simulated end
local function emit()counts.log_lines=counts.log_lines+1 end
local ensure=require('hd2runtime/api/ensure')
local plan=require('hd2runtime/api/plan')
local api=require('hd2runtime/api/hd2')
local watches
local wrapper=setmetatable({
 ensure=function(request)local w=ensure.start(runtime,emit,request);watches[#watches+1]=w;return w end,
 plan=function(request)local w=plan.start(runtime,emit,request);w.one_shot=true;watches[#watches+1]=w;return w end},
 {__index=api})
package.preload['mods/skyeshade/hd2runtime']=function()return wrapper end
local function copy(t)local r={};for k,v in pairs(t)do r[k]=v end;return r end
local function delta(a,b)local r={};for k,v in pairs(b)do r[k]=v-(a[k] or 0)end;return r end
local function metric_counters()return metrics and metrics.snapshot().counters or {} end
local FRAME=1/60
local function frame(state)
 local started=os.clock()
 simulated=simulated+FRAME
 for _,w in ipairs(watches)do
  if w.status~='rejected' and w.status~='cancelled' and w.status~='complete' then w.tick(FRAME)end
 end
 local cost=os.clock()-started
 if cost>state.worst then state.worst=cost end
end
local function settled()
 for _,w in ipairs(watches)do
  if w.one_shot then
   if w.status~='complete' and w.status~='rejected' then return false end
  elseif w.status~='rejected' and (w.runs<1 or w.status~='waiting') then return false end
 end
 return true
end
local function run_scenario(names,steady_seconds,reinitialize,keep_fingerprint)
 watches={};overlay={};protection={};reset_counts()
 local ok_fp,fingerprint=pcall(require,'hd2runtime/core/fingerprint')
 if not keep_fingerprint and ok_fp and fingerprint.reset then fingerprint.reset()end
 if metrics then metrics.reset()end
 for _,name in ipairs(names)do assert(loadstring(ADDONS[name],name))()end
 local startup={worst=0,frames=0}
 while not settled() do
  frame(startup);startup.frames=startup.frames+1
  assert(startup.frames<60*600,'startup did not settle')
 end
 local report={mods=names,startup={frames=startup.frames,seconds=startup.frames*FRAME,
  worst_frame_cpu=startup.worst,adapter=copy(counts),metrics=metric_counters()},watches={}}
 for _,w in ipairs(watches)do
  report.watches[#report.watches+1]={id=w.id,status=w.status,runs=w.runs,error=w.error,
   result=w.result and w.result.status,writes=w.result and w.result.writes}
 end
 local before,before_metrics=copy(counts),metric_counters()
 local steady={worst=0}
 for _=1,math.floor(steady_seconds/FRAME)do frame(steady)end
 report.steady={seconds=steady_seconds,worst_frame_cpu=steady.worst,adapter=delta(before,counts),
  metrics=delta(before_metrics,metric_counters()),watches={}}
 for _,w in ipairs(watches)do
  report.steady.watches[#report.steady.watches+1]={id=w.id,status=w.status,runs=w.runs,
   verifications=w.verifications,drifts=w.drifts,current_interval=w.current_interval}
 end
 if reinitialize then
  -- Simulate the game recreating its tables: every target returns to vanilla bytes.
  overlay={};protection={}
  local runs={};for i,w in ipairs(watches)do runs[i]=w.runs end
  local mark,mark_metrics=copy(counts),metric_counters()
  local state={worst=0};local seconds=0
  local function reapplied()
   for i,w in ipairs(watches)do
    if not w.one_shot and (w.status=='rejected' or w.runs<=runs[i]) then return false end
   end
   return true
  end
  while not reapplied() and seconds<3600 do frame(state);seconds=seconds+FRAME end
  local after={worst=0}
  for _=1,math.floor(600/FRAME)do frame(after)end
  report.reinitialize={detected_and_reapplied=reapplied(),seconds_to_reapply=seconds,
   adapter=delta(mark,counts),metrics=delta(mark_metrics,metric_counters()),
   worst_frame_cpu=state.worst,steady_after_worst_frame_cpu=after.worst}
 end
 return report
end
local result={scenarios={}}
local worker=coroutine.create(function()
 for _,name in ipairs(EXAMPLES)do
  result.scenarios[#result.scenarios+1]=run_scenario({name},STEADY_SECONDS,true)
 end
 result.scenarios[#result.scenarios+1]=run_scenario(EXAMPLES,STEADY_SECONDS,false)
 source.close()
 return result
end)
local ok,value
repeat ok,value=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,value);return json.encode(value)
'''


def audit(root, snapshot, steady_seconds):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
        + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources(root).items())
    addons = {name: (ROOT / 'examples/projects' / name / 'src/addon.lua').read_text() for name in EXAMPLES}
    program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve())
        + '\nlocal STEADY_SECONDS=' + str(steady_seconds)
        + '\nlocal EXAMPLES={' + ','.join(lua(name) for name in EXAMPLES) + '}'
        + '\nlocal ADDONS={' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in addons.items()) + '}\n'
        + PROGRAM)
    return json.loads(execute(program.encode()))


def module_bytes():
    sizes = [path.stat().st_size for path in (GAME / 'bin/helldivers2.exe', GAME / 'data/game/game.dll')
        if path.exists()]
    return sum(sizes) / 2 if len(sizes) == 2 else None


def summarize(result):
    per_hash = module_bytes()
    for scenario in result['scenarios']:
        for phase in ('startup', 'steady', 'reinitialize'):
            if phase in scenario and per_hash:
                scenario[phase]['module_hash_disk_bytes'] = scenario[phase]['adapter']['module_hashes'] * per_hash
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='source tree to audit (default: this tree)')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--steady-seconds', type=int, default=3600)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = summarize(audit(args.root.resolve(), args.snapshot, args.steady_seconds))
    result.update(steadySeconds=args.steady_seconds, snapshot=args.snapshot.name, mode='snapshot-overlay',
        researchWrites=0, gameProcessAccess=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    for scenario in result['scenarios']:
        steady = scenario['steady']['adapter']
        print(','.join(scenario['mods'])[:60], 'startup_hashes=%d' % scenario['startup']['adapter']['module_hashes'],
            'steady: queries=%d bytes=%d hashes=%d writes=%d protect=%d logs=%d' % (steady['queries'],
            steady['read_bytes'], steady['module_hashes'], steady['writes'], steady['protection_changes'],
            steady['log_lines']), [w['status'] for w in scenario['watches']])


if __name__ == '__main__':
    main()
