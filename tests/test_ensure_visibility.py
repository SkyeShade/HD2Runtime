"""An Editor may pause upkeep without interrupting requested operations."""
import unittest

from test_runtime_performance import check


class EnsureVisibilityTests(unittest.TestCase):
    def test_pending_recovery_runs_while_verification_is_paused(self):
        from test_retry_semantics import check as retry_check
        retry_check('''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
loaded=false
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0,recover={delay=10,max_delay=15}}
e.set_verification_enabled(false)
require('hd2runtime/runtime/scheduler').attach(e)
for _=1,1000 do update(0.1);if e.status=='recovering'then break end end
assert(e.status=='recovering'and e.recoveries==1,tostring(e.error))
loaded=true
for _=1,200 do update(0.1);if e.runs==1 then break end end
assert(e.runs==1 and e.status=='waiting','closed recovery did not finish');assert_values('new')
local reads0=runtime.reads
for _=1,100 do update(1)end
assert(runtime.reads==reads0,'settled recovery did not return to sleep')
''')

    def test_paused_watch_finishes_initial_apply_and_repairs_only_after_resume(self):
        check('''
require('hd2runtime/runtime/application_mode').configure(true)  -- the 0.40.0 optimizations (off by default)
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0,interval=1,max_interval=1}
e.set_verification_enabled(false)
require('hd2runtime/runtime/scheduler').attach(e)
for _=1,3000 do update(0);if e.runs==1 then break end end
assert(e.runs==1,tostring(e.error));assert_values('new')
local calls,tick=0,e.tick
e.tick=function(...)calls=calls+1;return tick(...)end
local reads0=runtime.reads
replace(targets.lifetime.address,targets.lifetime.old)
for _=1,3600 do update(1)end
assert(calls==0 and runtime.reads==reads0,'closed editor performs verification')
assert(e.runs==1 and e.drifts==0)
e.set_verification_enabled(true)
for _=1,3000 do update(0.01);if e.runs==2 then break end end
assert(e.runs==2 and e.drifts==1,'resume did not repair drift');assert_values('new')
local checks=e.verifications
for _=1,300 do update(0.01)end
assert(e.verifications-checks>=2 and e.verifications-checks<=3,'open interval differs from one second')
e.set_verification_enabled(false)
calls=0;reads0=runtime.reads
for _=1,100 do update(1)end
assert(calls==0 and runtime.reads==reads0)
e.cancel();update(0.01)
assert(require('hd2runtime/runtime/scheduler').active()==0,'closed cancel did not finish')
''')

    def test_paused_bound_watch_accepts_new_values_and_restore(self):
        check('''
local value=require('hd2runtime/api/options').value({id='visible-bound',min=90,max=300,step=1,default=180})
local e=hd2.ensure{patch=typed_cooldown('visible-bound',90,value),startup_delay=0,interval=1,max_interval=1}
e.set_verification_enabled(false)
require('hd2runtime/runtime/scheduler').attach(e)
for _=1,3000 do update(0);if e.runs==1 then break end end
assert(e.runs==1,tostring(e.error))
for _=1,100 do update(1)end
assert(value:set(200))
for _=1,4 do update(0.1)end
assert(e.runs==1,'sleep time consumed a new edit debounce')
for _=1,3000 do update(0.1);if e.runs==2 then break end end
assert(e.runs==2,tostring(e.error))
assert(runtime.read(targets.cooldown.address,4)==require('hd2runtime/core/bytes').encode(200,'f32'))
assert(value:set(90))
for _=1,3000 do update(0.1);if e.runs==3 then break end end
assert(e.runs==3 and runtime.read(targets.cooldown.address,4)==targets.cooldown.old,'closed restore failed')
''')
