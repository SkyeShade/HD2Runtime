"""Public API -> real shared engine -> guarded synthetic projectile memory."""
import unittest
from homing_test_support import ROOT,run
MODULES=('core/bytes','core/page_protection','core/guarded_transaction','runtime/metrics',
 'runtime/memory_watch','runtime/spawn_compatibility','domains/projectile_rows',
 'domains/projectile_homing','domains/event_natives','runtime/projectile_homing','api/homing',
 'runtime/homing_lock_policy','runtime/homing_lock','runtime/homing_aim','runtime/homing_view',
 'runtime/homing_los','runtime/homing_los_native','runtime/homing_los_pins')
PRELUDE="""
package.preload['hd2runtime/runtime/events']=function()return{owner=function(v)return v or'mods/test'end,emit_log=function()end}end
local make=(function()
"""+(ROOT/'tests/fixtures/homing_pool.lua').read_text()+"""
end)()
local f=make();f.engine.stop(f.config)
local api=require('hd2runtime/api/homing')
local h=api.homing('AR-23 Liberator',{acquisition='pre_fire',lock_time=.2,max_targets=3,
 cone=30,range=200,arm_distance=0,retarget=false,lateral_acceleration=600,turn_rate=1440})
assert(h.status=='active',h.reason)
f.engine.step(.01)
local function finish()
 for i=1,6 do f.engine.step(.06)end
 assert(#h:lock_state().locked==3)
 f.engine.step(.01)
end
"""
class LockIntegrationTests(unittest.TestCase):
 def test_observation_failure_drops_allocations_without_erasing_mission_totals(self):
  failures=(
   ('world', 'local previous=f.world_api.open;f.world_api.open=function()return nil end', 'f.world_api.open=previous'),
   ('game state', 'local previous=f.world_api.game_state;f.world_api.game_state=function()return nil end', 'f.world_api.game_state=previous'),
   ('proof', "local previous=f.engine.prove;f.engine.prove=function()return nil,'proof unavailable'end", 'f.engine.prove=previous'),
   ('counter', 'local previous=f.world_api.projectile_counter;f.world_api.projectile_counter=function()return nil end', 'f.world_api.projectile_counter=previous'),
   ('update', "local previous=f.world_api.game_state;f.world_api.game_state=function()error('unreadable state')end", 'f.world_api.game_state=previous'))
  for name,fail,restore in failures:
   with self.subTest(failure=name):
    self.check('''
finish();f.spawn();f.engine.step(.005)
local before=h:stats();local writes=#f.writes
assert(before.shots>0 and before.writes>0 and before.locks>0)
'''+fail+'''
f.watch.tick(.01)
local after=h:stats()
for _,key in ipairs({'shots','writes','locks'})do
 assert(after[key]==before[key],'temporary observation loss erased mission '..key)
end
local _,count=f.engine.tracked()
assert(count==0 and #h:lock_state().locked==0 and #f.writes==writes)
'''+restore+'''
f.engine.step(.01);finish();f.spawn();f.engine.step(.005)
assert(h:stats().writes>before.writes,'new observations must recover without old allocations')
f.world_api.game_state=function()return{mission=false,host=true,mode_entity=99}end
f.engine.step(.01)
assert(h:stats().shots==0 and h:stats().writes==0,'actual mission end must reset totals')
''')

 def test_los_uses_the_same_configured_aim_point_as_locks_and_steering(self):
  self.check('''
h:stop()
local rays={}
require('hd2runtime/runtime/homing_aim').visible=function(_,origin,point)
 rays[#rays+1]=point;return true,'clear'
end
h=api.homing('AR-23 Liberator',{acquisition='pre_fire',lock_time=0,max_targets=3,
 cone=30,range=200,aim_height=4,require_los=true})
for i=1,6 do f.engine.step(.06)end
local snapshot=h:lock_state();assert(#snapshot.locked==3 and #rays>=3)
for _,ray in ipairs(rays)do assert(ray.z==4,'LOS differs from configured aim point')end
for _,target in ipairs(snapshot.locked)do assert(target.position.z==4)end
''')

 def test_invalid_lock_options_do_not_replace_a_working_handle(self):
  self.check('''
for _,opts in ipairs({{acquisition=false},{acquisition='unknown'},{max_targets=2},
 {acquisition='pre_fire',max_targets=1.5},{acquisition='pre_fire',max_targets=7},
 {acquisition='pre_fire',require_los=1},{acquisition='pre_fire',lock_time=-1},
 {acquisition='pre_fire',target='friendly'},{acquisition='pre_fire',retarget=true},
 {acquisition='pre_fire',multiplayer=true},{acquisition='pre_fire',cone=31}})do
 local bad=api.homing('AR-23 Liberator',opts)
 assert(bad.status=='refused'and bad.code=='INVALID_OPTION')
 assert(h.status=='active','bad options stopped the previous configuration')
end
''')

 def test_unreadable_new_window_invalidates_allocated_rounds(self):
  self.check('''
finish();local slot=f.spawn();f.engine.step(.005);local n=#f.writes
f.spawn();f.unreadable_slots=true;f.engine.step(.01)
assert(#f.writes==n,'cannot keep steering when a possibly reused slot was not observed')
local _,count=f.engine.tracked();assert(count==0 and #h:lock_state().locked==0)
''')

 def test_snapshot_is_detached_and_replacement_invalidates_old_handle(self):
  self.check('''
finish();local snapshot=h:lock_state();assert(snapshot.frame==nil and snapshot.locked[1].descriptor==nil)
snapshot.locked[1].position.x=999;assert(h:lock_state().locked[1].position.x==100)
local old=h;h=api.homing('AR-23 Liberator',{acquisition='pre_fire',cone=30,range=200})
assert(old.status=='replaced'and #old:lock_state().locked==0 and h.status=='active')
''')

 def check(self,body):self.assertEqual(run(PRELUDE+body,MODULES),b'ok')
 def test_prelock_burst_assignments_are_independent_and_speed_preserving(self):
  self.check("""
local early=f.spawn();local original=f.records(early);f.engine.step(.01);assert(#f.writes==0)
finish();local slots={};for i=1,12 do slots[i]=f.spawn()end
f.engine.step(.005)
local tracked,count=f.engine.tracked();assert(count==12)
for i,slot in ipairs(slots)do
 assert(tracked[slot].target.entity==20+(i-1)%3)
 local x,y,z=f.velocity(slot);assert(y>0 and math.abs(math.sqrt(x*x+y*y+z*z)-100)<.001)
end
for k,v in pairs(original)do assert(f.records(early)[k]==v)end
assert(h:stats().writes==12)
""")
 def test_lost_owner_stops_old_rounds_and_no_retroactive_lock(self):
  self.check("""
finish();local slot=f.spawn();f.engine.step(.005);local n=#f.writes
f.world_api.equipped=function()return nil end
f.engine.step(.01);assert(#f.writes==n)
local _,count=f.engine.tracked();assert(count==0)
assert(#h:lock_state().locked==0)
""")
 def test_source_identity_race_and_stop_never_rewrite_foreign_round(self):
  self.check("""
finish();local slot=f.spawn();f.engine.step(.005);local n=#f.writes
f.scalar(f.system+f.PO.source.base+slot*f.PO.source.stride+f.PO.source.entity,999)
f.engine.step(.01);assert(#f.writes==n)
local fresh=f.spawn();f.engine.step(.005);assert(#f.writes>n)
h:stop();n=#f.writes;f.engine.step(.01);assert(#f.writes==n and h.status=='stopped')
""")
 def test_legacy_flight_acquisition_is_still_the_default(self):
  self.check("""
h:stop();h=api.homing('AR-23 Liberator',{arm_distance=0,cone=30,range=200})
assert(h.status=='active'and h:lock_state()==nil)
local slot=f.spawn();f.engine.step(.005);assert(h:stats().writes==1)
""")
