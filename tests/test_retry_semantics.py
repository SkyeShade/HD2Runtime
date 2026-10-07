"""Bounded retry semantics for guarded operations and ensure."""
import unittest

from support import ROOT, run


def check(body):
    return run((ROOT / 'tests/transaction_memory.lua').read_text() + '''
local module=runtime.module;local loaded=true;local not_ready_checks=0
runtime.module=function(name)
    if not loaded then not_ready_checks=not_ready_checks+1;return nil end
    return module(name)
end
local function tick(watch,seconds,step)
    step=step or 0.25
    for _=1,math.floor(seconds/step+0.5)do watch.tick(step)end
end
local function count_logs(text)
    local n=0;for _,line in ipairs(logs)do if line:find(text,1,true)then n=n+1 end end;return n
end
''' + body + "\nreturn 'ok'")


class RetrySemanticsTests(unittest.TestCase):
    def test_success_stops_after_first_attempt(self):
        check('''
local w=hd2.transaction(transaction_request())
tick(w,10)
assert(w.status=='complete' and w.attempts==1,'status='..w.status..' attempts='..w.attempts)
local reads,n=runtime.reads,#writes
tick(w,120);assert(runtime.reads==reads and #writes==n,'completed operation kept working')
assert(count_logs('retry')==0)
''')

    def test_transient_unavailability_retries_and_succeeds(self):
        check('''
loaded=false
local w=hd2.transaction(transaction_request())
tick(w,3.25)
assert(w.status=='retry_wait' and w.attempts==1,'first attempt '..w.status..' '..w.attempts)
assert(w.last_transient:find('TARGET_UNAVAILABLE',1,true))
tick(w,4.5);assert(w.attempts==1,'retried before the 5 second delay')
tick(w,1);assert(w.attempts==2)
tick(w,5);assert(w.attempts==3)
loaded=true
tick(w,10)
assert(w.status=='complete' and w.attempts==4,'status='..w.status..' attempts='..w.attempts)
assert(count_logs('retry 2/6')==1 and count_logs('retry 4/6')==1 and count_logs('retry 5/6')==0)
assert_values('new')
''')

    def test_transient_retries_are_bounded(self):
        check('''
loaded=false
local w=hd2.transaction(transaction_request())
tick(w,60)
assert(w.status=='rejected' and w.attempts==6,'status='..w.status..' attempts='..w.attempts)
assert(w.result.code=='TARGET_UNAVAILABLE' and w.result.attempts==6)
assert(#writes==0 and #protections==0)
local checks,reads=not_ready_checks,runtime.reads
tick(w,600);assert(not_ready_checks==checks and runtime.reads==reads,'kept polling after exhaustion')
''')

    def test_permanent_failures_fail_on_first_attempt(self):
        check('''
replace(targets.radius.address,string.char(1,2,3,4))
local w=hd2.transaction(transaction_request());tick(w,10)
assert(w.status=='rejected' and w.attempts==1 and w.result.code=='CONFLICT')
replace(targets.radius.address,targets.radius.old)
local hash=runtime.module_hash
-- A verified build is cached per process; model a process whose modules never matched.
require('hd2runtime/core/fingerprint').reset()
runtime.module_hash=function()return 'different build'end
w=hd2.transaction(transaction_request());tick(w,10)
assert(w.status=='rejected' and w.attempts==1,'fingerprint mismatch retried: '..w.attempts)
assert(w.error:find('unsupported build fingerprint',1,true))
runtime.module_hash=hash
assert(#writes==0 and count_logs('retry')==0)
''')

    def test_rolled_back_or_unsafe_failures_do_not_retry(self):
        run('''
local retry=require('hd2runtime/runtime/retry')
assert(retry.transient('TARGET_UNAVAILABLE: entity allocation absent')=='TARGET_UNAVAILABLE')
assert(retry.transient('x: unstable ownership/data snapshot')=='TARGET_UNSTABLE')
assert(retry.transient('TARGET_UNAVAILABLE: x',{rollback='verified',protection_restored=true}))
assert(retry.transient('TARGET_UNAVAILABLE: x',{rollback='refused_or_failed'})==nil)
assert(retry.transient('TARGET_UNAVAILABLE: x',{rollback='not_needed',protection_restored=false})==nil)
assert(retry.transient('CONFLICT: radius is neither expected nor desired')==nil)
assert(retry.transient('stratagem root identity changed')==nil)
assert(retry.transient('patch resolution budget exhausted')==nil)
return 'ok'
''')

    def test_queued_time_consumes_no_attempts(self):
        check('''
local exclusive=require('hd2runtime/runtime/exclusive')
local holder={}
assert(exclusive.acquire(holder))
local w=hd2.transaction(transaction_request())
tick(w,300)
assert(w.status=='queued' and w.attempts==0,'queued watch consumed attempts: '..w.attempts)
exclusive.release(holder)
tick(w,10)
assert(w.status=='complete' and w.attempts==1)
-- A retry wait releases the gate for other operations.
loaded=false
local a=hd2.transaction(transaction_request());tick(a,3.25)
assert(a.status=='retry_wait' and not exclusive.busy(),'retry wait holds the gate')
loaded=true;tick(a,10);assert(a.status=='complete')
''')

    def test_ensure_reset_reenters_the_same_bounded_retry_path(self):
        check('''
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0}
tick(e,5)
assert(e.runs==1 and e.status=='waiting');assert_values('new')
local n=#writes
-- The game resets a value while it is (re)loading: drift is detected, the full
-- guarded operation starts, and transient unavailability retries without ending ensure.
replace(targets.lifetime.address,targets.lifetime.old);loaded=false
tick(e,61)
assert(e.drifts==1 and e.status~='rejected','drift did not start guarded path: '..e.status)
tick(e,11)
assert(count_logs('retry 3/6')==1 and e.status~='rejected' and e.runs==1)
loaded=true
tick(e,10)
assert(e.runs==2 and #writes==n+1 and writes[#writes].field=='lifetime','runs='..e.runs)
assert(e.current_interval==60);assert_values('new')
-- If the game never becomes ready after a reset, ensure stops after six attempts.
replace(targets.lifetime.address,targets.lifetime.old);loaded=false
tick(e,61+60)
assert(e.status=='rejected' and e.result.code=='TARGET_UNAVAILABLE' and e.result.attempts==6,
    'status='..e.status)
local checks=not_ready_checks;tick(e,3600,1)
assert(not_ready_checks==checks,'ensure kept polling after exhausted retries')
''')

    def test_ensure_recover_starts_a_fresh_guarded_resolution_after_exhausted_retries(self):
        check('''
local seen={}
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0,recover={delay=10,max_delay=15},
    on_status=function(status,info)seen[#seen+1]=status..':'..tostring(info.code)..':'..tostring(info.previous)end}
loaded=false
tick(e,27)
assert(e.status=='recovering'and e.recoveries==1 and e.result.code=='TARGET_UNAVAILABLE','status='..e.status)
assert(e.retry_in and e.retry_in<=10,'retry_in '..tostring(e.retry_in))
assert(count_logs('recovery 1 in 10 update seconds')==1 and#writes==0)
-- Still not ready: the next wait doubles, up to max_delay.
tick(e,10+27)
assert(e.status=='recovering'and e.recoveries==2 and count_logs('recovery 2 in 15 update seconds')==1)
-- Ready again: the fresh resolution applies (every guard re-run) and the ensure keeps running.
loaded=true
tick(e,20)
assert(e.status=='waiting'and e.runs==1,'status='..e.status..' runs='..e.runs);assert_values('new')
assert(count_logs('recovering: fresh guarded resolution')==2)
local text=table.concat(seen,' ')
assert(text:find('recovering:TARGET_UNAVAILABLE',1,true)and text:find('waiting:',1,true),text)
''')

    def test_ensure_recover_never_covers_deterministic_failures_and_honours_its_limit(self):
        check('''
replace(targets.radius.address,string.char(1,2,3,4))
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0,recover=true}
tick(e,10)
assert(e.status=='rejected'and e.result.code=='CONFLICT'and e.recoveries==0,'a conflict is never recovered')
replace(targets.radius.address,targets.radius.old)
loaded=false
local limited=hd2.ensure{transaction=transaction_request(),startup_delay=0,recover={delay=1,limit=2}}
tick(limited,200)
assert(limited.status=='rejected'and limited.recoveries==2,'status='..limited.status..' '..limited.recoveries)
assert(#writes==0)
-- Invalid options are refused at registration.
local function refused(request)local ok,h=pcall(hd2.ensure,request);return not ok or h.status=='rejected'end
for _,bad in ipairs({{delay=0},{limit=0},{max_delay=1,delay=5},{wait=3},'yes'})do
    assert(refused{transaction=transaction_request(),recover=bad},'recover '..tostring(bad))
end
assert(refused{transaction=transaction_request(),on_status=42})
-- A failing on_status is logged and changes nothing.
loaded=true
local f=hd2.ensure{transaction=transaction_request(),startup_delay=0,on_status=function()error('cb broke')end}
tick(f,5);assert(f.status=='waiting'and f.runs==1 and count_logs('on_status failed')>=1)
''')

    def test_recoverable_classification(self):
        run('''
local ensure=require('hd2runtime/api/ensure')
local moved='ownership/context or non-target bytes changed'
assert(ensure.recoverable(moved,{rollback='verified',protection_restored=true}))
assert(ensure.recoverable(moved,{rollback='not_needed'}))
assert(not ensure.recoverable(moved,{rollback='refused_or_failed'}))
assert(not ensure.recoverable(moved,{rollback='verified',protection_restored=false}))
assert(ensure.recoverable('x',{code='TARGET_UNSTABLE',rollback='not_needed'}))
assert(ensure.recoverable('x',{code='TARGET_UNAVAILABLE'}))
assert(not ensure.recoverable('CONFLICT: radius',{code='CONFLICT'}))
assert(not ensure.recoverable('unsupported build fingerprint',{code='VALIDATION_FAILED'}))
assert(not ensure.recoverable('ASSET_UNAVAILABLE: x',{code='ASSET_UNAVAILABLE'}))
return 'ok'
''')

    def test_plan_retries_transiently_and_counts_attempts(self):
        check('''
loaded=false
local plan=hd2.plan{id='retry-plan',operations={
    {id='cooldown',target=hd2.stratagem('FX-12 Shield Generator Relay'),
     field=hd2.fields.stratagem.definition_cooldown,expect=90,value=180}}}
tick(plan,3.25);assert(plan.status=='retry_wait' and plan.attempts==1,plan.status)
loaded=true;tick(plan,10)
assert(plan.status=='complete' and plan.attempts==2,'status='..plan.status..' '..tostring(plan.error))
''')


if __name__ == '__main__':
    unittest.main()
