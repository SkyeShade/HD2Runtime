"""Pre-fire acquisition must reuse the shared scan and bound fresh game reads."""
import unittest
from homing_test_support import run

PRELUDE = '''
local Lock=require('hd2runtime/runtime/homing_lock')
local reads={state=0,position=0,exists=0,network=0}
local w={};local items={}
for i=1,256 do items[i]={entity=i,unit=1000+i,x=50,y=0,z=0,at=1}end
local world={
 entity_state=function(_,entity)
  reads.state=reads.state+1
  return{life=0,descriptor={pointer=2000+entity,unit=1000+entity}}
 end,
 entity_exists=function()reads.exists=reads.exists+1;return true end,
 unit_position=function()reads.position=reads.position+1;return{x=50,y=0,z=0}end,
 entity_network=function(_,entity)reads.network=reads.network+1;return entity end}
local aim={capture=function()return{session_key='test',origin={x=0,y=0,z=0},
 forward={x=1,y=0,z=0},weapon_id=900,weapon_unit=901}end,
 visible=function()return true,'clear'end}
local deps={world=world,aim=aim,weapon={sources={'test'}},position_age=.5,
 config={enabled=true,mode='multi',max_targets=6,lock_time=0,range=100,half_angle=12}}
local c=Lock.new(deps)
'''


class LockBudgetTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(PRELUDE + body, ('runtime/homing_lock_policy', 'runtime/homing_lock')), b'ok')

    def test_dense_candidate_scan_bounds_fresh_game_reads(self):
        self.check('''
assert(c.hooks.before(w,1,items))
assert(c:status().locked==6)
assert(reads.state<=8 and reads.position<=8 and reads.exists<=8 and reads.network<=8,
 'pre-fire must not reread every enemy in the shared scan')
''')

    def test_duplicate_cached_rows_cannot_exceed_the_validation_budget(self):
        self.check('''
for i=2,256 do items[i]=items[1]end
c.hooks.before(w,1,items);assert(c:status().locked==1)
local before=reads.state;c.hooks.before(w,1.01,items)
assert(reads.state-before<=8,'retained locks must also deduplicate cached rows')
''')

    def test_blocked_front_candidates_do_not_starve_later_clear_target(self):
        self.check('''
for i=256,10,-1 do items[i]=nil end
deps.config.require_los=true;deps.config.lock_time=.3
local ninth_seen=false
aim.visible=function(_,origin,point,current,unit)
 if unit==1009 then ninth_seen=true;return true,'clear'end
 return false,'blocked'
end
c=Lock.new(deps)
for i=0,30 do
 local now=1+i*.05;for _,item in ipairs(items)do item.at=now end
 local before=reads.state;c.hooks.before(w,now,items)
 assert(reads.state-before<=8,'rotation must stay inside the validation budget')
end
assert(ninth_seen and c:status().locked==1,'later clear candidates need forward progress')
assert(c:visual_snapshot().locked[1].entity==9)
''')

    def test_rotating_other_candidates_preserves_continuous_acquisition(self):
        self.check('''
for i,item in ipairs(items)do item.y=i*.01 end
world.unit_position=function(_,unit)return{x=50,y=(unit-1000)*.01,z=0}end
deps.config.lock_time=.6;c=Lock.new(deps)
for i=0,30 do
 local now=1+i*.05;for _,item in ipairs(items)do item.at=now end
 c.hooks.before(w,now,items)
end
assert(c:status().locked==6,'candidate rotation must preserve active acquisition timers')
for _,target in ipairs(c:visual_snapshot().locked)do assert(target.entity<=6)end
''')

    def test_stale_future_and_out_of_cone_cache_entries_never_trigger_fresh_reads(self):
        self.check('''
for i,item in ipairs(items)do
 if i%3==0 then item.at=0 elseif i%3==1 then item.at=2 else item.y=100 end
end
c.hooks.before(w,1,items)
assert(c:status().locked==0,'unusable cached positions must not acquire')
assert(reads.state==0 and reads.position==0 and reads.exists==0 and reads.network==0)
''')

    def test_selected_target_is_rechecked_before_a_stale_lock_can_be_used(self):
        self.check('''
world.entity_state=function(_,entity)return{life=2,descriptor={pointer=2000+entity,unit=1000+entity}}end
c.hooks.before(w,1,items)
assert(c:status().locked==0)
world.entity_state=function(_,entity)return{life=0,descriptor={pointer=2000+entity,unit=9999}}end
c.hooks.before(w,1.01,items)
assert(c:status().locked==0,'a reused entity with another unit is not the cached candidate')
''')
