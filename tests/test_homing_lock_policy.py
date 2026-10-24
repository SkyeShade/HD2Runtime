import unittest
from homing_test_support import run

PRELUDE=r'''
local policy=require('hd2runtime/runtime/homing_lock_policy')

          s=policy.new()
          cfg={enabled=true,mode='single',lock_time=.3,max_targets=3,
               half_angle=12,range=100,require_los=true}
          function target(k,a,d)
            return {key=k,net=tonumber(k) or 10,node=16,angle_deg=a or 1,
                    distance=d or 10,alive=true,visible=true}
          end
          function step(t, items) return policy.step(s,t,items or {target('1')},cfg) end

'''

class PolicyTests(unittest.TestCase):
    def check(self,code):
        self.assertEqual(run(PRELUDE+code,('runtime/homing_lock_policy',)),b'ok')

    def test_acquisition_waits_for_configured_time(self):
        self.check('''
          assert(#step(1).locked==0)
          local mid=step(1.15); assert(#mid.acquiring==1)
          assert(mid.acquiring[1].progress>.49 and mid.acquiring[1].progress<.51)
          local done=step(1.31); assert(#done.locked==1 and #done.acquiring==0)
          assert(done.locked[1].key=='1' and done.locked[1].acquired_at==1.31)
        ''')

    def test_single_selects_angle_then_distance_then_identity(self):
        self.check('''
          cfg.lock_time=0
          local a=step(1,{target('3',3,1),target('2',1,9),target('1',1,9)})
          assert(#a.locked==1 and a.locked[1].key=='1')
          a=step(2,{target('1',1,10),target('2',1,9)})
          assert(a.locked[1].key=='2')
        ''')

    def test_missing_dead_unknown_los_and_outside_cone_never_lock(self):
        self.check('''
          cfg.lock_time=0
          local a,b,c,d,e=target('1'),target('2'),target('3'),target('4'),target('5')
          a.alive=false; b.visible=nil; c.distance=101; d.angle_deg=13; e.visible=false
          assert(#step(1,{a,b,c,d,e}).locked==0)
        ''')

    def test_reentry_and_changed_identity_restart_acquisition(self):
        self.check('''
          step(1); assert(#step(1.31).locked==1)
          step(1.4,{}); assert(#step(1.5).locked==0)
          assert(#step(1.81).locked==1)
          local changed=target('1'); changed.net=22
          assert(#step(1.9,{changed}).locked==0)
        ''')

    def test_configuration_change_restarts_lock_and_limits_targets(self):
        self.check('''
          cfg.mode='multi'; cfg.lock_time=0
          local items={target('3',3),target('1',1),target('2',2)}
          assert(#step(1,items).locked==3)
          cfg.max_targets=2
          assert(#step(1.1,items).locked==2)
          cfg.lock_time=.5
          assert(#step(1.2,items).locked==0)
          step(1.6,items)
          assert(#step(1.71,items).locked==2)
        ''')

    def test_disabled_and_invalid_configs_clear_existing_locks(self):
        self.check('''
          cfg.lock_time=0; assert(#step(1).locked==1)
          cfg.enabled=false; assert(#step(2).locked==0)
          cfg.enabled=true; cfg.lock_time=0/0
          local a=step(3); assert(#a.locked==0 and a.reason=='invalid_config')
          cfg.lock_time=.3; assert(#step(4).locked==0)
        ''')

    def test_time_reversal_and_explicit_reset_clear_acquisition(self):
        self.check('''
          step(10); assert(#step(10.31).locked==1)
          assert(#step(2).locked==0)
          assert(#step(2.31).locked==1)
          policy.reset(s,'new_session'); assert(#step(2.4).locked==0)
        ''')

    def test_config_rejects_nonfinite_and_invalid_types(self):
        self.check('''
          for _, item in ipairs({{'lock_time',math.huge},{'lock_time',-1},
            {'max_targets',7},{'max_targets',1.5},{'half_angle',-2},
            {'range',0},{'mode','unknown'},{'enabled',1},{'require_los','yes'}}) do
            local c={}; for k,v in pairs(cfg) do c[k]=v end
            c[item[1]]=item[2]
            local valid,why=policy.validate_config(c)
            assert(valid==nil and type(why)=='string',item[1])
          end
          local c=assert(policy.validate_config({}))
          assert(c.enabled==false and c.require_los==false and c.lock_time==.3)
        ''')

    def test_burst_assigns_each_new_generation_round_robin(self):
        self.check('''
          cfg.mode='multi'; cfg.lock_time=0
          step(1,{target('3',3),target('2',2),target('1',1)})
          for i=1,6 do
            local t,why=policy.assign(s,'bullet:'..i,1.01)
            assert(t.key==tostring((i-1)%3+1) and why=='assigned')
          end
          local t,why=policy.assign(s,'bullet:1',1.02)
          assert(t==nil and why=='duplicate_projectile')
          assert(policy.assign(s,'bullet:7',1.03).key=='1')
        ''')

    def test_single_mode_assigns_rapid_rounds_to_same_target(self):
        self.check('''
          cfg.lock_time=0; step(1)
          for i=1,30 do assert(policy.assign(s,'bullet:'..i,1.01).key=='1') end
        ''')

    def test_angle_changes_do_not_reorder_already_selected_group(self):
        self.check('''
          cfg.mode='multi'; cfg.lock_time=0
          step(1,{target('1',1),target('2',2),target('3',3)})
          assert(policy.assign(s,'p1',1).key=='1')
          step(1.1,{target('3',1),target('2',2),target('1',3)})
          assert(policy.assign(s,'p2',1.1).key=='2')
          assert(policy.assign(s,'p3',1.1).key=='3')
        ''')

    def test_dead_or_occluded_target_removed_before_next_bullet(self):
        self.check('''
          cfg.mode='multi'; cfg.lock_time=0
          step(1,{target('1'),target('2'),target('3')})
          assert(policy.assign(s,'p1',1).key=='1')
          local dead=target('2'); dead.alive=false
          local hidden=target('3'); hidden.visible=false
          step(1.1,{target('1'),dead,hidden})
          assert(policy.assign(s,'p2',1.1).key=='1')
        ''')

    def test_duplicate_candidate_identity_not_duplicate_lock(self):
        self.check('''
          cfg.mode='multi'; cfg.lock_time=0
          assert(#step(1,{target('1'),target('1')}).locked==1)
          local conflicting=target('1'); conflicting.net=2
          assert(#step(1.1,{target('1'),conflicting}).locked==0)
        ''')

    def test_snapshot_is_detached_from_caller_mutations(self):
        self.check('''
          cfg.lock_time=0; local a=target('1')
          local status=step(1,{a}); a.net=99; status.locked[1].net=88
          local t=policy.assign(s,'p1',1); assert(t.net==1); t.net=77
          assert(policy.assign(s,'p2',1).net==1)
        ''')

    def test_no_assignment_before_lock_or_after_disable(self):
        self.check('''
          step(1); local t,why=policy.assign(s,'p1',1)
          assert(t==nil and why=='no_locked_target')
          step(1.31); cfg.enabled=false; step(1.32)
          t,why=policy.assign(s,'p2',1.32); assert(t==nil and why=='disabled')
        ''')

    def test_observation_gaps_do_not_count_as_continuous_lock(self):
        self.check('''
          step(1); assert(#step(3).locked==0)
          step(3.31)
          local t,why=policy.assign(s,'p1',3.9)
          assert(t==nil and why=='stale_snapshot')
        ''')

    def test_invalid_time_or_key_cannot_assign_or_keep_stale_lock(self):
        self.check('''
          cfg.lock_time=0; step(1)
          local t,why=policy.assign(s,'',1); assert(t==nil and why=='invalid_projectile_key')
          t,why=policy.assign(s,'p',0/0); assert(t==nil and why=='invalid_time')
          t,why=policy.assign(s,'p',1); assert(t==nil)
          step(10); t,why=policy.assign(s,'p',9)
          assert(t==nil and why=='time_reversal')
        ''')

    def test_tracking_is_bounded_and_expired_generations_are_removed(self):
        self.check('''
          cfg.lock_time=0; step(1)
          for i=1,policy.MAX_TRACKED do assert(policy.assign(s,'p:'..i,1)) end
          local t,why=policy.assign(s,'overflow',1)
          assert(t==nil and why=='tracking_capacity')
          step(1+policy.PROJECTILE_TTL+1)
          assert(policy.assign(s,'new_generation',1+policy.PROJECTILE_TTL+1))
        ''')

    def test_invalid_target_numbers_and_unknown_alive_are_rejected(self):
        self.check('''
          cfg.mode='multi'; cfg.lock_time=0
          local a,b,c,d=target('1'),target('2'),target('3'),target('4')
          a.net=0/0; b.distance=math.huge; c.alive=nil; d.node=-1
          assert(#step(1,{a,b,c,d}).locked==0)
          local e=target('5'); e.visible=nil
          cfg.require_los=false; assert(#step(1.1,{e}).locked==1)
        ''')
