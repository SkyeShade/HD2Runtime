"""Steady-state cost regressions: ensured mods must go idle once their targets are stable."""
import json
import unittest

from support import ROOT, run


def check(body):
    return run((ROOT / 'tests/transaction_memory.lua').read_text() + '''
local hash=runtime.module_hash;local hashes=0
runtime.module_hash=function(name)hashes=hashes+1;return hash(name)end
local query=runtime.query;local queries=0
runtime.query=function(at)queries=queries+1;return query(at)end
local function typed_cooldown(id,expect,value)
    return {id=id or 'typed-cooldown',target=hd2.stratagem('FX-12 Shield Generator Relay'),
        field=hd2.fields.stratagem.definition_cooldown,expect=expect or 90,value=value or 180}
end
''' + body + "\nreturn 'ok'")


class RuntimePerformanceTests(unittest.TestCase):
    def test_scheduler_sleeps_ensures_but_keeps_deadlines_and_drift_recovery(self):
        check('''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0,interval=2,max_interval=8}
require('hd2runtime/runtime/scheduler').attach(e)
for _=1,3000 do update(0);if e.runs==1 then break end end
assert(e.runs==1,tostring(e.error))
local calls,tick=0,e.tick
e.tick=function(...)calls=calls+1;return tick(...)end
local reads0=runtime.reads
for _=1,100 do update(0.01)end
assert(calls==0 and runtime.reads==reads0,'sleeping ensure still does work')
for _=1,110 do update(0.01)end
assert(calls==1 and e.verifications==1,'deadline not honored')
assert(e.current_interval==4 and e.runs==1,'stable check did not back off')
replace(targets.lifetime.address,targets.lifetime.old)
for _=1,3000 do update(0.01);if e.runs==2 then break end end
assert(e.runs==2 and e.drifts==1,'sleeping ensure did not recover drift')
assert_values('new')
local n=calls;e.cancel();update(0.01)
assert(calls==n+1 and require('hd2runtime/runtime/scheduler').active()==0,
 'cancelled sleeping ensure did not finish cleanup immediately')
''')

    def test_sleeping_bound_ensure_wakes_without_consuming_new_option_debounce(self):
        check('''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local value=require('hd2runtime/api/options').value({id='cooldown',min=90,max=300,step=1,default=180},'mods/test/sleep')
local notices=0
local e=hd2.ensure{patch=typed_cooldown('sleep-bound',90,value),startup_delay=0,interval=30,
 on_status=function()notices=notices+1 end}
require('hd2runtime/runtime/scheduler').attach(e)
for _=1,3000 do update(0);if e.runs==1 then break end end
assert(e.runs==1,tostring(e.error))
local n=e.debug().ticks
for _=1,100 do update(0.1)end
assert(e.debug().ticks==n,'idle bound ensure kept ticking')
assert(value:set(200))
for _=1,4 do update(0.1)end
assert(e.runs==1,'old sleeping time consumed the new debounce')
for _=1,3000 do update(0.1);if e.runs==2 then break end end
assert(e.runs==2 and notices>0,'new option did not wake the sleeping ensure')
assert(runtime.read(targets.cooldown.address,4)==require('hd2runtime/core/bytes').encode(200,'f32'))
''')

    def test_scheduler_keeps_sleep_time_separate_from_child_frame_time(self):
        run('''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local scheduler=require('hd2runtime/runtime/scheduler')
local seen={}
local w={status='waiting',_sleep_for=5}
function w.cancel()w.status='cancelled'end
function w.tick(dt,skipped)seen={dt,skipped};w.status='complete'end
scheduler.attach(w)
for _=1,4 do update(1)end
assert(#seen==0)
update(1)
assert(seen[1]==1 and seen[2]==4,'sleep inflated a child operation frame')
assert(scheduler.active()==0 and update==nil,'completed sleeper left scheduler attached')
return 'ok'
''')

    def test_blocked_bound_ensure_sleeps_until_its_value_changes(self):
        check('''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local value=require('hd2runtime/api/options').value({id='blocked',min=90,max=300,step=1,default=180})
replace(targets.cooldown.address,string.char(1,2,3,4))
local e=hd2.ensure{patch=typed_cooldown('blocked-sleep',90,value),startup_delay=0,recover=true}
require('hd2runtime/runtime/scheduler').attach(e)
for _=1,3000 do update(0);if e.status=='blocked'then break end end
assert(e.status=='blocked'and e.result.code=='CONFLICT',tostring(e.error))
local ticks,reads=e.debug().ticks,runtime.reads
for _=1,100 do update(0.1)end
assert(e.debug().ticks==ticks and runtime.reads==reads,'blocked ensure kept polling')
replace(targets.cooldown.address,targets.cooldown.old)
assert(value:set(200))
for _=1,3000 do update(0.1);if e.runs==1 then break end end
assert(e.runs==1 and e.status=='waiting','blocked ensure did not wake on option change')
''')

    def test_typed_stratagem_cooldown_applies_end_to_end(self):
        # Regression: the stratagem row used to be captured twice, so the guarded
        # transaction found two contexts and refused every typed cooldown write.
        check('''
local w=finish(hd2.patch(typed_cooldown()))
assert(w.status=='complete' and w.result.status=='APPLIED',tostring(w.error))
assert(#writes==1 and writes[1].field=='cooldown')
assert(runtime.read(targets.cooldown.address,4)==targets.cooldown.new)
''')

    def test_ensured_mod_is_idle_after_steady_state(self):
        check('''
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0}
for _=1,3000 do e.tick(0);if e.runs==1 then break end end
assert(e.runs==1 and e.status=='waiting',tostring(e.error));assert_values('new')
local writes0,protections0,hashes0,queries0,logs0=#writes,#protections,hashes,queries,#logs
local reads0=runtime.reads
for _=1,24*3600 do e.tick(1)end
assert(e.runs==1,'full resolution repeated in steady state: '..e.runs)
assert(hashes==hashes0,'module hashed in steady state')
assert(#writes==writes0 and #protections==protections0,'writes/protection changes in steady state')
assert(e.current_interval==600,'interval did not back off: '..e.current_interval)
assert(e.verifications>0 and e.verifications<=160,'verifications='..e.verifications)
local per=(runtime.reads-reads0)/e.verifications
assert(per<=8,'steady verification reads too much: '..per)
assert((queries-queries0)/e.verifications<=8,'steady verification queries too much')
assert(#logs-logs0<=1,'steady state logs every cycle: '..(#logs-logs0))
-- A game reinitialization (target back to vanilla) is detected and fully reapplied.
replace(targets.lifetime.address,targets.lifetime.old)
for _=1,700 do e.tick(1);if e.runs==2 then break end end
assert(e.runs==2 and e.drifts==1 and #writes==writes0+1 and writes[#writes].field=='lifetime')
assert(e.current_interval==60,'interval not reset after drift')
assert_values('new');protection_is(2)
''')

    def test_fingerprint_hashed_once_per_process(self):
        check('''
local w=transaction();assert(w.status=='complete',w.error)
local first=hashes;assert(first==2,'first operation hashed '..first)
for target_name,target in pairs(targets)do replace(target.address,target.old)end
w=transaction();assert(w.status=='complete',w.error)
w=finish(hd2.patch(typed_cooldown('again')));assert(w.result.status=='ALREADY_DESIRED',tostring(w.error))
assert(hashes==first,'module files re-hashed: '..hashes)
local m=hd2.metrics().counters
assert(m['fingerprint.module_hashes']==2 and m['fingerprint.cache_hits']>=4)
''')

    def test_operations_are_serialized_and_gate_released(self):
        check('''
local a=hd2.transaction(transaction_request())
local b=hd2.patch(typed_cooldown('queued'))
a.tick(3.1);b.tick(3.1)
assert(b.status=='queued','second operation was not queued: '..b.status)
finish(a);assert(a.status=='complete',a.error)
finish(b);assert(b.status=='complete' and b.result.status=='ALREADY_DESIRED',tostring(b.error))
-- Cancellation and rejection release the gate.
local c=hd2.patch(typed_cooldown('cancelled'));c.tick(3.1);assert(c.status~='queued');c.cancel()
replace(targets.cooldown.address,string.char(1,2,3,4))
local d=finish(hd2.patch(typed_cooldown('rejected')))
assert(d.status=='rejected' and d.result.code=='CONFLICT')
replace(targets.cooldown.address,targets.cooldown.old)
local f=finish(hd2.patch(typed_cooldown('after')))
assert(f.status=='complete' and f.result.status=='APPLIED',tostring(f.error))
-- Time spent queued does not consume the resolution budget.
for _,target in pairs(targets)do replace(target.address,target.old)end
local g=hd2.transaction(transaction_request());g.tick(3.1)
local h=hd2.patch(typed_cooldown('long-wait'))
for _=1,400 do h.tick(1)end
assert(h.status=='queued','budget consumed while queued: '..h.status)
finish(g);finish(h);assert(h.status=='complete',tostring(h.error))
''')

    def test_steady_state_audit_on_real_snapshot(self):
        audit = json.loads((ROOT / 'validation/steady-state-audit.json').read_text())
        self.assertGreaterEqual(audit['steadySeconds'], 3600)
        self.assertFalse(audit['gameProcessAccess'])
        for scenario in audit['scenarios']:
            name = ','.join(scenario['mods'])
            for watch in scenario['watches']:
                self.assertNotEqual(watch['status'], 'rejected', (name, watch))
            steady = scenario['steady']
            for key in ('module_hashes', 'writes', 'identical_writes', 'protection_changes'):
                self.assertEqual(steady['adapter'][key], 0, (name, key))
            for key in ('discover.walks', 'entity_catalog.captures', 'stratagem.table_captures',
                    'transaction.applies', 'ensure.full_resolutions'):
                self.assertEqual(steady['metrics'].get(key, 0), 0, (name, key))
            if 'reinitialize' in scenario:
                self.assertTrue(scenario['reinitialize']['detected_and_reapplied'], name)
                self.assertEqual(scenario['reinitialize']['adapter']['module_hashes'], 0, name)
        combined = audit['scenarios'][-1]
        self.assertEqual(len(combined['mods']), 7)
        self.assertEqual(combined['startup']['adapter']['module_hashes'], 2)
        before = json.loads((ROOT / 'validation/steady-state-audit-before-0.23.0-22ec478.json').read_text())
        self.assertGreater(before['scenarios'][-1]['steady']['adapter']['module_hashes'], 100)

    def test_read_slices_keep_the_quantum_and_extend_only_within_the_tick_budget(self):
        run(r'''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local metrics=require('hd2runtime/runtime/metrics')
local scheduler=require('hd2runtime/runtime/scheduler')
local Reader=require('hd2runtime/runtime/reader')
local now,queries,bytes=0,0,0
local rt={}
function rt.query(at)
    queries=queries+1
    if at>=0x1000000 then return {base=0x1000000,size=0x1000000,allocation_base=0x1000000,state=0x1000,type=0x20000,protect=4}end
    return {base=at-at%4096,size=4096,allocation_base=at-at%4096,state=0x1000,type=0x20000,protect=4}
end
function rt.read(at,n)bytes=bytes+n;return string.rep('\0',n)end
-- Per resume: the queries (or bytes) one slice issued.
local function slices(work,opts)
    opts=opts or{}
    local co=coroutine.create(work)
    local per={}
    local function step()
        local q,b=queries,bytes
        assert(coroutine.resume(co))
        per[#per+1]=opts.bytes and(bytes-b)or(queries-q)
    end
    if opts.outside then
        while coroutine.status(co)~='dead'do step()end
        return per
    end
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()step();if coroutine.status(co)=='dead'then watch.status='complete'end end
    scheduler.attach(watch)
    for _=1,100000 do if watch.status=='complete'then break end;update(1/60)end
    assert(watch.status=='complete','slices did not finish')
    return per
end
local function many(cost)
    return function()
        local r=Reader.new(rt)
        for i=1,3000 do r.query(0x100000+i*4096);now=now+(cost or 0)end
    end
end
local function largest(per)local m=0;for _,v in ipairs(per)do if v>m then m=v end end;return m end
local function smallest_full(per)local m=math.huge;for i=1,#per-1 do if per[i]<m then m=per[i]end end;return m end
-- No precise clock: exactly the base quantum (64 queries), as before 0.30.
assert(scheduler.tick_seconds()==nil,'tick time outside a tick')
local per=slices(many())
assert(largest(per)==64 and smallest_full(per)==64,'no clock: '..largest(per)..'/'..smallest_full(per))
metrics.set_clock(function()return now end)
-- Outside an update tick the quantum applies even with a clock.
per=slices(many(),{outside=true})
assert(largest(per)==64,'outside a tick: '..largest(per))
-- A tick that is not spending time (a clock that does not move): up to the hard ceiling, never past it.
per=slices(many())
assert(largest(per)==Reader.MAX_OPERATIONS and #per<=4,'free clock: '..largest(per)..' in '..#per)
-- 10 us per query: the slice ends once the tick has spent SLICE_SECONDS (about 100 queries).
per=slices(many(0.00001))
assert(largest(per)>64 and largest(per)<=102 and smallest_full(per)>=99,'1 ms slice: '..largest(per)..'/'..smallest_full(per))
-- 100 us per query (a slow machine): the base quantum still runs every tick, never less than before.
per=slices(many(0.0001))
assert(largest(per)==64 and smallest_full(per)==64,'slow machine: '..largest(per)..'/'..smallest_full(per))
-- Bytes: a slice reads at most MAX_BYTES (2 MiB) however cheap the tick is.
per=slices(function()Reader.new(rt).read({base=0x1000000,size=0x1000000},0,4*1048576)end,{bytes=true})
assert(largest(per)==Reader.MAX_BYTES and #per==math.ceil(4*1048576/Reader.MAX_BYTES),'bytes per slice: '..largest(per)..' in '..#per)
local mode=require('hd2runtime/runtime/application_mode')
mode.configure(false)
per=slices(function()Reader.new(rt).read({base=0x1000000,size=0x1000000},0,4*1048576)end,{bytes=true})
assert(largest(per)==1048576 and #per==4,'diagnostic mode did not restore the old byte ceiling')
mode.configure(true)
-- ... and without a clock exactly the 64 KiB quantum.
metrics.set_clock(function()return nil end)
per=slices(function()Reader.new(rt).read({base=0x1000000,size=0x1000000},0,1048576)end,{bytes=true})
assert(largest(per)==65536 and #per==16,'no clock bytes: '..largest(per)..' in '..#per)
return 'ok'
''')

    def test_burst_admission_budgets_new_jobs_but_never_starves_the_first(self):
        run(r'''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local metrics=require('hd2runtime/runtime/metrics')
local gate=require('hd2runtime/runtime/exclusive')
local scheduler=require('hd2runtime/runtime/scheduler')
local clock=0;metrics.set_clock(function()return clock end)
local completed=0
for i=1,10 do
 local w={status='waiting'}
 function w.cancel()w.status='cancelled';gate.release(w)end
 function w.tick()
  if gate.acquire(w)then
   clock=clock+0.0008;completed=completed+1;w.status='complete';gate.release(w)
  end
 end
 scheduler.attach(w)
end
update(1/60);assert(completed==2,'a burst ignored its combined budget: '..completed)
-- Unrelated expensive work precedes pending operations; at least one is admitted every frame.
local busy={status='waiting',tick=function()clock=clock+0.010 end,cancel=function()end}
scheduler.attach(busy)
for expected=3,10 do update(1/60);assert(completed==expected,'pending writes starved')end
assert(not gate.busy())
return 'ok'
''')

    def test_discovery_reads_each_header_once_and_shares_only_proven_keys(self):
        run(r'''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local b=require('hd2runtime/core/bytes')
local metrics=require('hd2runtime/runtime/metrics')
local discover=require('hd2runtime/runtime/discover')
local Reader=require('hd2runtime/runtime/reader')
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function framing(kind,size)return 'LDLD'..u32(1)..u32(kind)..u32(size-28)..u32(1)..u32(0)end
local function settings(kind,size)return {size=size,stride=8,groups={{offset=4,header=b.hex(framing(kind,size))}}}end
local map='MAPH'..string.rep('m',24)
local profile={entity_region_size=0x10000,map_header=b.hex(map),settings={
    alpha=settings(0xA1,0x3000),   -- window 0x3000..0x13000
    beta=settings(0xB2,0x5000),    -- window 0x5000..0x15000
    gamma=settings(0xC3,0x40000)}} -- window 0x40000..0x50000
local function table_bytes(kind,size)return u32(1)..framing(kind,size)..string.rep('\0',size-28)end
local regions={
    {base=0x100000,size=0x10000,data=map},
    {base=0x200000,size=0x4000,data=table_bytes(0xA1,0x3000)},  -- alpha's window only
    {base=0x300000,size=0x6000,data=table_bytes(0xB2,0x5000)},  -- alpha's and beta's windows
    {base=0x400000,size=0x40000,data=table_bytes(0xC3,0x40000)},-- gamma's window only
    {base=0x500000,size=0x8000,data=string.rep('x',28)},        -- alpha's and beta's windows, no table
}
local now,reads,header_reads=0,0,{}
local rt={}
function rt.system_info()return 4096,0x600000 end
function rt.monotonic_time()return now end
function rt.query(at)
    local previous=65536
    for _,r in ipairs(regions)do
        if at<r.base then return {base=previous,size=r.base-previous,allocation_base=0,state=0x10000,type=0,protect=1}end
        if at<r.base+r.size then return {base=r.base,size=r.size,allocation_base=r.base,state=0x1000,type=0x20000,protect=4}end
        previous=r.base+r.size
    end
    return {base=previous,size=0x600000-previous,allocation_base=0,state=0x10000,type=0,protect=1}
end
function rt.read(at,n)
    reads=reads+1
    for _,r in ipairs(regions)do
        if at>=r.base and at+n<=r.base+r.size then
            if at==r.base and n==28 then header_reads[r.base]=(header_reads[r.base]or 0)+1 end
            local data=r.data..string.rep('\0',r.size-#r.data)
            return data:sub(at-r.base+1,at-r.base+n)
        end
    end
    error('read outside the synthetic regions')
end
local function locate(needed,adapter,view)
    adapter=adapter or rt;view=view or profile
    local co=coroutine.create(function()return discover.locate(adapter,Reader.new(adapter),view,needed)end)
    while true do
        local ok,result=coroutine.resume(co);assert(ok,result)
        if coroutine.status(co)=='dead'then return result end
    end
end
local function counter(name)return metrics.snapshot().counters[name]or 0 end
-- A walk needing alpha and beta reads every header in their windows once (not once per key).
local found=locate({entity=true,alpha=true,beta=true})
assert(found.alpha.owner.base==0x200000 and found.beta.owner.base==0x300000 and found.entity.base==0x100000)
assert(found.alpha.records and found.beta.records,'needed tables are captured and parsed')
for base,count in pairs(header_reads)do assert(count==1,('header of 0x%X read %d times'):format(base,count))end
assert(header_reads[0x300000]==1 and header_reads[0x500000]==1 and header_reads[0x400000]==nil,'gamma window read')
assert(counter('discover.walks')==1)
-- New walk: beta's whole window was read for alpha, so beta is proven and shared; gamma's was not.
now=100;header_reads={}
found=locate({entity=true,alpha=true})
assert(counter('discover.walks')==2 and header_reads[0x400000]==nil)
now=101
found=locate({entity=true,beta=true})
assert(counter('discover.walks')==2 and counter('discover.shared_reuses')==1,'beta was not shared')
assert(found.beta.owner.base==0x300000 and found.beta.records,'a shared key is captured and parsed again')
found=locate({entity=true,gamma=true})
assert(counter('discover.walks')==3,'gamma was shared without its window being read')
assert(found.gamma.owner.base==0x400000)
-- A walk needing only beta does not read alpha's own region (outside beta's window): alpha stays unproven.
now=200;locate({entity=true,beta=true})
assert(counter('discover.walks')==4)
now=201;locate({entity=true,alpha=true})
assert(counter('discover.walks')==5,'alpha was shared without its window being read')
-- Sharing still expires 15 s after the walk started.
now=230;locate({entity=true,alpha=true});assert(counter('discover.walks')==6)
now=246;locate({entity=true,alpha=true});assert(counter('discover.walks')==7,'shared past 15 s')
-- A shared key is re-validated: a changed header falls back to a full walk.
now=247;regions[3].data=string.rep('y',28);local w=counter('discover.walks')
local ok=pcall(locate,{entity=true,beta=true})
assert(counter('discover.walks')==w+1,'changed header reused')
assert(not ok,'changed table header was accepted')
regions[3].data=table_bytes(0xB2,0x5000)
now=300
local view=setmetatable({components={}},{__index=profile})
local adapter=setmetatable({},{__index=rt})
local before=counter('discover.walks')
locate({entity=true,alpha=true})
locate({entity=true,alpha=true},rt,view)
locate({entity=true,alpha=true},adapter,profile)
assert(counter('discover.walks')==before+3,'different adapters/profiles shared an unproven walk')
for i=1,5 do
 locate({entity=true,alpha=true})
 locate({entity=true,alpha=true},rt,view)
 locate({entity=true,alpha=true},adapter,profile)
end
assert(counter('discover.walks')==before+3,'alternating domains discarded valid discovery proofs')
now=316
locate({entity=true,alpha=true})
locate({entity=true,alpha=true},rt,view)
locate({entity=true,alpha=true},adapter,profile)
assert(counter('discover.walks')==before+6,'a profile cache extended another cache lifetime')
-- Live APIs make a wrapper per operation. Only an explicit common address-space token can share their proofs.
local space={}
local a=setmetatable({_discovery_space=space},{__index=rt})
local c=setmetatable({_discovery_space=space},{__index=rt})
before=counter('discover.walks')
locate({entity=true,alpha=true},a,profile)
locate({entity=true,alpha=true},c,profile)
assert(counter('discover.walks')==before+1,'live wrappers did not share their completed walk')
-- The diagnostic switch drops existing proofs and never shares while off.
local mode=require('hd2runtime/runtime/application_mode')
mode.configure(false)
before=counter('discover.walks');local hits=counter('discover.shared_reuses')
locate({entity=true,alpha=true},a);locate({entity=true,alpha=true},c)
assert(counter('discover.walks')==before+2 and counter('discover.shared_reuses')==hits)
mode.configure(true)
locate({entity=true,alpha=true},a);locate({entity=true,alpha=true},c)
assert(counter('discover.walks')==before+3,'re-enable reused an old proof or did not rebuild sharing')


return 'ok'
''')

    def test_without_the_optimizations_every_watch_ticks_bursts_are_unbudgeted_and_paused_ensures_verify(self):
        # 0.40.1: off by default, the 0.31 behaviour (runtime/application_mode.lua).
        check('''
local mode=require('hd2runtime/runtime/application_mode')
assert(mode.enabled()==false,'the optimizations are off by default')
local scheduler=require('hd2runtime/runtime/scheduler')
-- A sleeping watch still ticks every frame, with no skipped time.
local seen={}
local w={status='waiting',_sleep_for=5}
function w.cancel()w.status='cancelled'end
function w.tick(dt,skipped)seen[#seen+1]=skipped;w._sleep_for=5;if #seen==4 then w.status='complete'end end
scheduler.attach(w)
for _=1,4 do update(1)end
assert(#seen==4 and seen[1]==0 and seen[4]==0,'a sleeping watch skipped frames: '..#seen)
-- Every operation of a burst is admitted in the same update, whatever the time spent.
local metrics=require('hd2runtime/runtime/metrics')
local gate=require('hd2runtime/runtime/exclusive')
local clock=0;metrics.set_clock(function()return clock end)
local completed=0
for _=1,10 do
 local job={status='waiting'}
 function job.cancel()job.status='cancelled';gate.release(job)end
 function job.tick()
  if gate.acquire(job)then clock=clock+0.0008;completed=completed+1;job.status='complete';gate.release(job)end
 end
 scheduler.attach(job)
end
update(1/60);assert(completed==10,'a burst was budgeted: '..completed)
metrics.set_clock(function()return nil end)
-- An ensure whose verification is paused (the editor's hidden window) keeps verifying.
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0,interval=1,max_interval=1}
e.set_verification_enabled(false)
scheduler.attach(e)
for _=1,3000 do update(0);if e.runs==1 then break end end
assert(e.runs==1,tostring(e.error))
replace(targets.lifetime.address,targets.lifetime.old)
for _=1,3000 do update(0.01);if e.runs==2 then break end end
assert(e.runs==2 and e.drifts==1,'a paused ensure stopped verifying without the optimizations')
assert_values('new')
e.cancel();update(0.01)
''')

    def test_native_readonly_wrappers_share_process_discovery_identity(self):
        run(r'''
local create=require('hd2runtime/runtime/windows_readonly')
local a,c=create(),create()
assert(a~=c and type(a._discovery_space)=='table'and a._discovery_space==c._discovery_space,
 'per-operation native wrappers must share address-space identity')
assert(a.write==nil and c.write==nil,'read-only adapter gained write access')
return 'ok'
''')

    def test_metrics_are_exported_without_process_access(self):
        run('''
local hd2=require('hd2runtime/api/hd2')
local m=hd2.metrics()
assert(type(m.counters)=='table' and type(m.worst_seconds)=='table')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
