"""Aim gates new acquisition/assignment, independently of the optional HUD."""
import unittest
from homing_test_support import run
from test_homing_lock_integration import MODULES, PRELUDE

EXTRA=('runtime/homing_reticle_style','runtime/homing_reticle','api/homing_reticle',
       'runtime/homing_visibility','runtime/homing_aim_state','domains/input_bindings')
SETUP=PRELUDE+'''
local aiming,aim_why=true,'native_aim_action_2_8'
package.loaded['hd2runtime/runtime/homing_aim_state']={active=function()return aiming,aim_why end}
require('hd2runtime/runtime/events').frame=function()return{cancel=function()end}end
local function configure(required)
 h:stop()
 h=api.homing('AR-23 Liberator',{acquisition='pre_fire',lock_time=.2,max_targets=3,
  cone=30,range=200,arm_distance=0,require_aim=required})
 assert(h.status=='active',h.reason)
 f.engine.step(.01)
end
configure(true)
'''


class RequireAimTests(unittest.TestCase):
    def check(self,body):
        self.assertEqual(run(SETUP+body,MODULES+EXTRA),b'ok')

    def test_inactive_or_unknown_aim_never_assigns_new_rounds_and_recovers(self):
        for value,reason in (('false','not_aiming'),('nil','aim_state_unavailable')):
            with self.subTest(aim=value):
                self.check('''
aiming='''+value+''';aim_why='aim_state_unavailable'
for i=1,6 do f.engine.step(.06)end
local state=h:lock_state()
assert(state.aim_active==aiming and state.aim_reason==aim_why)
assert(state.reason=='''+repr(reason)+''' and #state.locked==0 and #state.acquiring==0)
local hip=f.spawn();local before=f.records(hip);f.engine.step(.005)
assert(h:stats().writes==0 and h:stats().locks==0)
for k,v in pairs(before)do assert(f.records(hip)[k]==v)end
aiming=true;finish();f.spawn();f.engine.step(.005)
assert(h:stats().writes>0 and h:lock_state().aim_active==true)
''')

    def test_release_preserves_existing_round_but_reaim_restarts_acquisition(self):
        self.check('''
finish();local launched=f.spawn();f.engine.step(.005);local before=#f.writes
aiming=false;f.engine.step(.01)
local tracked,count=f.engine.tracked()
assert(count==1 and tracked[launched] and #f.writes>before,'already allocated round stopped on release')
assert(#h:lock_state().locked==0 and #h:lock_state().acquiring==0)
local hip=f.spawn();local original=f.records(hip);f.engine.step(.005)
tracked,count=f.engine.tracked();assert(count==1 and not tracked[hip])
aiming=true;f.engine.step(.05)
assert(#h:lock_state().locked==0 and #h:lock_state().acquiring==3,'reaim reused an old lock timer')
finish()
for k,v in pairs(original)do assert(f.records(hip)[k]==v,'hip-fired round acquired retroactively')end
assert(h:stats().locks==1)
''')

    def test_reader_failure_clears_old_locks_and_denies_new_rounds(self):
        self.check('''
finish()
require('hd2runtime/runtime/homing_aim_state').active=function()error('unreadable aim state')end
f.engine.step(.01)
local state=h:lock_state()
assert(state.aim_active==nil and state.aim_reason=='aim_state_read_failed')
assert(state.reason=='aim_state_read_failed'and #state.locked==0)
f.spawn();f.engine.step(.005);assert(h:stats().writes==0 and h:stats().locks==0)
''')

    def test_unknown_aim_preserves_prior_round_but_owner_and_source_checks_still_apply(self):
        self.check('''
finish();local launched=f.spawn();f.engine.step(.005);local before=#f.writes
aiming=nil;aim_why='aim_input_code_changed';f.engine.step(.01)
assert(#f.writes>before and h:lock_state().aim_active==nil)
assert(h:lock_state().reason=='aim_input_code_changed')
f.scalar(f.system+f.PO.source.base+launched*f.PO.source.stride+f.PO.source.entity,999)
before=#f.writes;f.engine.step(.01);assert(#f.writes==before)
local _,count=f.engine.tracked();assert(count==0)
aiming=true;finish();f.spawn();f.engine.step(.005)
aiming=false;f.world_api.equipped=function()return nil end
before=#f.writes;f.engine.step(.01);assert(#f.writes==before)
_,count=f.engine.tracked();assert(count==0,'aim release bypassed lost owner guard')
''')

    def test_hiding_optional_hud_does_not_disable_aimed_homing(self):
        self.check('''
local hud=h:reticle({aim_only=true});hud:hide()
finish();f.spawn();f.engine.step(.005)
assert(h:stats().writes>0 and h:lock_state().aim_active==true)
assert(not hud:status().visible)
''')

    def test_explicit_false_and_omission_preserve_hip_fire_behavior(self):
        self.check('''
aiming=false;configure(false);finish();f.spawn();f.engine.step(.005)
assert(h:stats().writes>0 and h.options.require_aim==false)
configure(nil);finish();f.spawn();f.engine.step(.005)
assert(h:stats().writes>0 and h.options.require_aim==false)
''')

    def test_option_is_boolean_and_pre_fire_only(self):
        self.check('''
for _,opts in ipairs({{require_aim=true},{require_aim=false},
 {acquisition='pre_fire',require_aim='yes'},{acquisition='pre_fire',require_aim=1}})do
 local bad=api.homing('AR-23 Liberator',opts)
 assert(bad.status=='refused'and bad.code=='INVALID_OPTION')
 assert(h.status=='active')
end
assert(h:describe().options.require_aim==true)
''')
