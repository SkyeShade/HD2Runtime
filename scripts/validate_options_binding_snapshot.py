"""Validate option-bound ensures against the retained snapshot and the real Mod Options Menu code.

Nothing touches a game process. Writes land in a copy-on-write overlay of the snapshot with page
protections, as in the booster and packaged-runtime validators. CowboyBingus Mod Options Menu
(`ModOptionsMenu`, api 1) is loaded from its own source (a local checkout, not vendored):
registration, validation, the saved-values file and get/set/on_change are its code. Its native
menu hook verifies game.dll in the current process and fails closed here, exactly as on an
unsupported build. A player's APPLY is reproduced the way the addon performs it: the applied
value is stored and every on_change callback runs once.

Covered: persisted and malformed saved values, defaults, live changes (owned-byte transitions),
no-op and rapid changes, drift after a change, disable/restore/re-enable, a reset while
disabled, changes while the target is unavailable, conflicts, transactions, plans and
acknowledgement guards.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_entity_authoring_snapshot import SNAPSHOT, lua, sources

OUTPUT = ROOT / 'validation/options-binding-snapshot.json'
MOM = Path(os.environ.get('MOD_OPTIONS_MENU',
    r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\bingus\ModOptionsMenu'))

PROGRAM = r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local b=require('hd2runtime/core/bytes')
local json=require('hd2runtime/primary_mapper/json')
local metrics=require('hd2runtime/runtime/metrics')
local fingerprint=require('hd2runtime/core/fingerprint')

-- Copy-on-write overlay with page protections (same contract as the booster validator).
local PAGE=4096
local overlay,protection={}, {}
local runtime={mode='snapshot-overlay'}
local tamper={}
local counts={writes=0,protection_changes=0}
local simulated=0
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)
 if tamper.unavailable and name=='game.dll'then return nil end
 return source.module(name)
end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)return source.module_hash(handle)end
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
local function reset_game()overlay={};protection={};fingerprint.reset()end

-- Bingus loader surface used by Mod Options Menu: api 1, version, log directory, open_log.
rawset(_G,'CowboyBingusModLoader',{api=1,version=18,modules={},log_directory=LOG_DIRECTORY,
 open_log=function()return nil end})
rawset(_G,'update',nil)
assert(loadstring(MOM_SOURCE,'@mods/cowboybingus/mod_options_menu'))()
local menu=assert(rawget(_G,'ModOptionsMenu'),'Mod Options Menu did not load')
assert(menu.api==1 and not menu.ready(),'menu integration must fail closed outside the game')
-- Record callbacks so APPLY can be reproduced exactly as the addon's changed() does it.
local callbacks={}
local on_change=menu.on_change
menu.on_change=function(id,fn)
 callbacks[id]=callbacks[id]or{};table.insert(callbacks[id],fn)
 return on_change(id,fn)
end
local function apply(id,value)
 if menu.get(id)==value then return end
 assert(menu.set(id,value))
 for _,fn in ipairs(callbacks[id]or{})do fn(menu.get(id),id)end
end

local scheduler=require('hd2runtime/runtime/scheduler')
local ensure=require('hd2runtime/api/ensure')
local hd2=require('hd2runtime/api/hd2')
local FRAME=0.1
local function frames(seconds)
 for _=1,math.floor(seconds/FRAME+0.5)do simulated=simulated+FRAME;update(FRAME)end
end
local database=require('hd2runtime/domains/booster_authoring')
local dll=source.module('game.dll')
local function scalar(name)
 local row=database.boosters[name].targets.tuning.fields
 local _,field=next(row)
 local at=dll+database.native.tableRva+field.backing.row*database.native.stride+8
 return b.value(runtime.read(at,4),0,'f32'),at
end
local function near(a,c)return math.abs(a-c)<1e-4 end
local function counter(name)return metrics.snapshot().counters[name]or 0 end
-- Run frames until an operation is idle again (discovery of heap tables spans many ticks).
local function settle(w,limit)
 local spent=0
 repeat frames(1);spent=spent+1 until (w.status~='running'and w.status~='waiting')or
  (w.status=='waiting'and w.runs>0 and spent>=1)or spent>=(limit or 600)
end
local function watch(request)
 return scheduler.attach(ensure.start(runtime,function()end,request))
end
local result={status='VALIDATED',mode='snapshot-overlay',snapshot=SNAPSHOT_NAME,fixtureFallback='disabled',
 modOptionsMenu={api=menu.api,version=menu.version,nativeReady=menu.ready()},checks={}}
local function check(name,ok,detail)
 result.checks[#result.checks+1]={name=name,passed=ok==true,detail=detail}
 assert(ok,name..(detail and(': '..tostring(detail))or''))
end

local worker=coroutine.create(function()
 local page=hd2.options({id='hd2rt_opts',title='Runtime Options Test'})
 local vitality=page:slider({id='vitality',label='Damage Taken',min=0.5,max=1,step=0.05,default=0.9,
  description='Vitality Enhancement damage multiplier.'})
 local enabled=page:toggle({id='enabled',label='Enabled',default=true})
 local extraction=page:choice({id='extraction',label='Extraction',choices={'Stock','Fast','Instant-ish'},
  values={0.7,0.5,0.2},default=1})
 local stamina=page:slider({id='stamina',label='Stamina',min=1,max=3,step=0.1,default=1.3})
 local mode=page:choice({id='mode',label='Mode',choices={'A','B'},default=1})
 local cap=page:slider({id='cap',label='Sample Cap',min=0,max=50,step=5,default=10})
 local radius=page:slider({id='radius',label='Firebomb Radius',min=2,max=6,step=1,default=2})
 local outer=page:slider({id='outer',label='Firebomb Outer',min=4,max=8,step=1,default=4})
 -- Mod Options Menu registers on the first update ticks, reading its saved-values file.
 frames(0.2)
 check('options registered with saved values',vitality.registered and near(vitality:get(),0.8)
  and vitality.source=='saved','value='..tostring(vitality:get()))
 check('malformed saved choice falls back to the default',mode:index()==1 and mode.source=='saved')
 check('out-of-range saved slider is clamped by the menu',cap:get()==50,'cap='..tostring(cap:get()))
 check('missing saved value uses the default',extraction:get()==0.7 and stamina:get()==1.3)

 -- Bound patch: persisted 0.8 is applied once after the startup delay.
 local baseline=scalar('Vitality Enhancement')
 local w=watch({enabled=enabled,startup_delay=1,patch={id='opt-vitality',allow_unverified_effect=true,
  target=hd2.booster('Vitality Enhancement'):tuning(),field=hd2.fields.booster.damage_taken_scale,
  expect=0.9,value=vitality}})
 frames(3)
 check('initial apply uses the saved value',w.runs==1 and near(scalar('Vitality Enhancement'),0.8),
  'value='..scalar('Vitality Enhancement'))
 check('baseline expect never mutates',near(baseline,0.9))

 -- Live change: an owned-byte transition, not a conflict.
 local owned=counter('options.owned_transitions');local resolutions=counter('options.bound_resolutions')
 apply('hd2rt_opts.vitality',0.75);frames(2)
 check('live change writes the new value',near(scalar('Vitality Enhancement'),0.75)and w.status=='waiting')
 check('change from an applied value is an owned transition',counter('options.owned_transitions')==owned+1)
 check('one resolution per applied change',counter('options.bound_resolutions')==resolutions+1)

 -- No-op change: same value never triggers work.
 resolutions=counter('options.bound_resolutions');local writes=counts.writes
 apply('hd2rt_opts.vitality',0.75);frames(2)
 check('no-op change does no work',counter('options.bound_resolutions')==resolutions and counts.writes==writes)

 -- Rapid changes inside the debounce window coalesce into one resolution.
 resolutions=counter('options.bound_resolutions')
 apply('hd2rt_opts.vitality',0.7);frames(0.1);apply('hd2rt_opts.vitality',0.65);frames(0.1)
 apply('hd2rt_opts.vitality',0.6);frames(2)
 check('rapid changes coalesce',counter('options.bound_resolutions')==resolutions+1
  and near(scalar('Vitality Enhancement'),0.6))

 -- Steady state stays idle, then a simulated reset re-applies the current desired value.
 local ticks=counter('ensure.full_resolutions');local verifications=w.verifications;frames(70)
 check('steady state is a byte check, not a resolution',counter('ensure.full_resolutions')==ticks
  and w.verifications>verifications and near(scalar('Vitality Enhancement'),0.6))
 reset_game();frames(250)
 check('drift after a change re-applies the new desired value',w.drifts>=1 and near(scalar('Vitality Enhancement'),0.6))

 -- Disable: guarded restore of the reviewed baseline, then dormant.
 apply('hd2rt_opts.enabled',false);frames(2)
 check('disable restores the reviewed baseline',near(scalar('Vitality Enhancement'),0.9)and w.status=='disabled'
  and w.restores==1)
 writes=counts.writes;reset_game();frames(30)
 check('a reset while disabled writes nothing',counts.writes==writes and near(scalar('Vitality Enhancement'),0.9))
 apply('hd2rt_opts.vitality',0.55);frames(2)
 check('a value change while disabled stays dormant',counts.writes==writes and w.status=='disabled')
 apply('hd2rt_opts.enabled',true);frames(2)
 check('re-enable applies the current value',near(scalar('Vitality Enhancement'),0.55)and w.status=='waiting')

 -- Target unavailable: the change waits in retry and applies once the target is back.
 tamper.unavailable=true;apply('hd2rt_opts.vitality',0.5);frames(2)
 check('change while the target is unavailable waits',w.status=='running'and near(scalar('Vitality Enhancement'),0.55))
 apply('hd2rt_opts.vitality',0.65);frames(1)
 tamper.unavailable=false;frames(8)
 check('pending retry picks up the newest value',near(scalar('Vitality Enhancement'),0.65)and w.status=='waiting')
 -- Disable while a retry is pending: the pending apply is dropped and the owned value restored.
 tamper.unavailable=true;apply('hd2rt_opts.vitality',0.7);frames(2)
 apply('hd2rt_opts.enabled',false);frames(1);tamper.unavailable=false;frames(8)
 check('disable during a pending retry restores the baseline',near(scalar('Vitality Enhancement'),0.9)
  and w.status=='disabled')
 apply('hd2rt_opts.enabled',true);frames(2)

 -- Conflict: a third-party value blocks the operation (no write); the next change retries.
 local _,at=scalar('Vitality Enhancement')
 overlay[at]=b.encode(0.33,'f32');writes=counts.writes
 apply('hd2rt_opts.vitality',0.6);frames(2)
 check('a third-party value is a conflict',w.status=='blocked'and counts.writes==writes
  and near(scalar('Vitality Enhancement'),0.33),w.error)
 overlay[at]=nil;apply('hd2rt_opts.vitality',0.65);frames(2)
 check('the next change after a conflict applies',w.status=='waiting'and near(scalar('Vitality Enhancement'),0.65))
 w.cancel()

 -- Plan: two bound operations stay one atomic write set; one change re-resolves both.
 local plan=watch({startup_delay=0,plan={id='opt-plan',operations={
  {id='extraction',target=hd2.booster('Expert Extraction Pilot'):tuning(),allow_unverified_effect=true,
   field=hd2.fields.booster.extraction_time_scale,expect=0.7,value=extraction},
  {id='stamina',target=hd2.booster('Stamina Enhancement'):tuning(),allow_unverified_effect=true,
   field=hd2.fields.booster.stamina_scale,expect=1.3,value=stamina}}}})
 settle(plan)
 apply('hd2rt_opts.extraction',2);apply('hd2rt_opts.stamina',1.6);frames(1);settle(plan)
 check('plan applies every bound value atomically',near(scalar('Expert Extraction Pilot'),0.5)
  and near(scalar('Stamina Enhancement'),1.6)and plan.status=='waiting'and plan.result.status=='APPLIED')
 plan.cancel()

 -- Transaction on a shared settings row: both radii in one guarded write set.
 local tx=watch({startup_delay=0,transaction={id='opt-firebomb',target=hd2.booster('Firebomb Hellpods'):explosion(),
  allow_shared=true,allow_unverified_effect=true,changes={
   {field=hd2.fields.explosion.inner_radius,expect=2,value=radius},
   {field=hd2.fields.explosion.outer_radius,expect=4,value=outer}}}})
 settle(tx)
 check('transaction first run is a guarded no-op at the defaults',tx.runs==1 and tx.result.status=='ALREADY_DESIRED',
  tostring(tx.status)..' '..tostring(tx.error))
 apply('hd2rt_opts.radius',3);apply('hd2rt_opts.outer',6);frames(1);settle(tx)
 check('transaction applies both bound fields in one write set',tx.status=='waiting'and tx.runs==2
  and tx.result.status=='APPLIED'and tx.result.writes==2,tostring(tx.status)..' '..tostring(tx.error))
 tx.cancel()

 -- Guards cannot be bypassed by binding.
 local function rejects(request,needle)
  local ok,why=pcall(ensure.start,runtime,function()end,request)
  return not ok and tostring(why):find(needle,1,true)~=nil,tostring(why)
 end
 check('allow_shared stays mandatory',rejects({transaction={id='no-shared',
  target=hd2.booster('Firebomb Hellpods'):explosion(),allow_unverified_effect=true,
  changes={{field=hd2.fields.explosion.inner_radius,expect=2,value=radius}}}},'allow_shared'))
 check('allow_unverified_effect stays mandatory',rejects({patch={id='no-effect',
  target=hd2.booster('Vitality Enhancement'):tuning(),field=hd2.fields.booster.damage_taken_scale,
  expect=0.9,value=vitality}},'allow_unverified_effect'))
 local wide=page:slider({id='wide',label='Wide',min=0,max=10,step=1,default=1})
 check('slider range must fit the reviewed field range',rejects({patch={id='wide',allow_unverified_effect=true,
  target=hd2.booster('Integrated Extinguishers'):tuning(),field=hd2.fields.booster.burn_decay_bonus,
  expect=0.5,value=wide}},'reviewed range'))
 local fraction=page:slider({id='fraction',label='Fraction',min=0,max=20,step=0.5,default=1})
 check('integer fields reject fractional sliders',rejects({patch={id='fraction',allow_unverified_effect=true,
  target=hd2.booster('Increased Reinforcement Budget'):tuning(),field=hd2.fields.booster.reinforcements_per_player,
  expect=1,value=fraction}},'integer'))
 local uses=page:slider({id='uses',label='Uses',min=1,max=10,step=1,default=2})
 check('read-only capabilities stay read-only',rejects({patch={id='ro',target=hd2.stratagem('Eagle Airstrike'),
  field=hd2.fields.stratagem.max_uses,expect=0,value=uses}},'field is read-only'))
 check('fields a target does not expose stay unavailable',rejects({patch={id='other',allow_unverified_effect=true,
  target=hd2.booster('Vitality Enhancement'):tuning(),field=hd2.fields.booster.stamina_scale,
  expect=1.3,value=stamina}},'not exposed'))
 local ok,why=pcall(hd2.patch,{id='one-shot',allow_unverified_effect=true,target=hd2.booster('Vitality Enhancement'):tuning(),
  field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vitality})
 check('one-shot operations refuse option handles',not ok and tostring(why):find('require hd2.ensure',1,true)~=nil)

 -- The menu saves applied values only while its native integration is active (in game on the
 -- supported build); outside the game it keeps them in memory. Reading saved values is covered above.
 result.persistence={readSavedValues=true,writeBackExercised=false,
  reason='Mod Options Menu saves only while its native menu integration is active'}
 result.metrics={}
 for key,value in pairs(metrics.snapshot().counters)do
  if key:find('^options%.')or key:find('^ensure%.')then result.metrics[key]=value end
 end
 result.writes=counts.writes;result.protectionChanges=counts.protection_changes
 source.close()
 return result
end)
local ok,out=coroutine.resume(worker)
assert(ok,out);assert(coroutine.status(worker)=='dead','validation yielded')
return json.encode(out)
'''


def validate(snapshot, mom=MOM):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    source = (mom / 'src/mod_options_menu.lua').read_text(encoding='latin-1')
    commit = subprocess.run(['git', '-C', str(mom), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as folder:
        # Saved values as a previous session left them: one valid, one malformed, one out of range.
        Path(folder, 'ModOptionsMenu.values').write_text(
            'hd2rt_opts.cap\t99\nhd2rt_opts.mode\tbanana\nhd2rt_opts.vitality\t0.8\n', newline='\n')
        preload = '\n'.join('package.preload[' + lua(name) + ']=function(...) return assert(loadstring('
            + lua(body) + ',' + lua(name) + '))(...) end' for name, body in sources().items())
        program = (preload + '\nlocal SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal SNAPSHOT_NAME='
            + lua(Path(snapshot).name) + '\nlocal LOG_DIRECTORY=' + lua(Path(folder).as_posix())
            + '\nlocal MOM_SOURCE=' + lua(source) + '\n' + PROGRAM)
        result = json.loads(execute(program.encode()))
    result['modOptionsMenu']['sourceCommit'] = commit
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = validate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
