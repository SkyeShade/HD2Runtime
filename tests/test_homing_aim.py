import unittest
from homing_test_support import run

PRELUDE=r'''
local aim=require('hd2runtime/runtime/homing_aim')

          world={key='module-session',view={},
            state={mission=true,host=true,mode_entity=300},
            list={{['local']=true,peer='00000000000000A1',avatar=100}},
            held={entity=200,type='968211C0033DCE64'},unit=400,
            pose={position={x=2,y=3,z=4},forward={x=0,y=1,z=0}},exists=true}
          package.preload['hd2runtime/runtime/event_world']=function()
            return {
              game_state=function(w) return w.state end,
              players=function(w,avatars) assert(avatars==true); return w.list end,
              entity_exists=function(w,id) return w.exists end,
              equipped=function(w,id)
                assert(id==100); w.equipped_calls=(w.equipped_calls or 0)+1
                if w.equipped_calls>1 and w.switched then return w.switched end
                return w.held
              end,
              entity_unit=function(w,id) if id==100 then return 300 end;assert(id==200);return w.unit end,
              unit_pose=function(w,id) assert(id==400); return w.pose end
            }
          end
          package.preload.ffi=function() error('FFI must never load in these tests') end

'''

class AimTests(unittest.TestCase):
    def test_weapon_identity_comes_from_the_requested_catalogue_not_ar23(self):
        self.check('''
world.held.type='1122334455667788'
assert(aim.capture(world,{['1122334455667788']=true}))
assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
''')

    def check(self,code):
        self.assertEqual(run(PRELUDE+code,('runtime/homing_aim',)),b'ok')

    def test_held_ar23_root_pose_and_session_are_returned(self):
        self.check('''
          local a=assert(aim.capture(world,{['968211C0033DCE64']=true}))
          assert(a.weapon_id==200 and a.avatar_id==100 and a.weapon_unit==400 and a.avatar_unit==300)
          assert(a.origin.x==2 and a.origin.y==3 and a.forward.y==1)
          assert(a.aim_basis=='weapon_root' and type(a.session_key)=='string')
          a.origin.x=99; assert(world.pose.position.x==2)
        ''')

    def test_ship_multiplayer_and_unknown_host_are_rejected(self):
        self.check('''
          world.state.mission=false; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
          world.state.mission=true; world.state.host=nil; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
          world.state.host=true; world.list[2]={avatar=101}; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
        ''')

    def test_wrong_held_weapon_is_not_satisfied_by_ar23_inventory(self):
        self.check('''
          world.held.type='NOT_AR23'; local a,why=aim.capture(world,{['968211C0033DCE64']=true})
          assert(a==nil and why=='configured_weapon_not_held')
        ''')

    def test_missing_identity_and_destroyed_avatar_are_rejected(self):
        self.check('''
          world.list[1]['local']=false; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
          world.list[1]['local']=true; world.exists=false; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
          world.exists=true; world.state.mode_entity=nil; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
        ''')

    def test_weapon_switch_during_read_rejects_old_pose(self):
        self.check('''
          world.switched={entity=201,type='968211C0033DCE64'}
          local a,why=aim.capture(world,{['968211C0033DCE64']=true}); assert(a==nil and why=='held_weapon_changed')
        ''')

    def test_unknown_pose_nan_and_scaled_forward_are_rejected(self):
        self.check('''
          world.pose.position.x=0/0; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
          world.pose.position.x=2; world.pose.forward.y=100; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
          world.pose=nil; assert(aim.capture(world,{['968211C0033DCE64']=true})==nil)
        ''')

    def test_unavailable_los_is_unknown_never_clear(self):
        self.check('''
          local clear,why=aim.visible(world,{x=0,y=0,z=0},{x=0,y=10,z=0})
          assert(clear==nil and why=='los_unavailable')
          assert(package.loaded.ffi==nil)
        ''')

    def test_reader_failure_becomes_unknown(self):
        self.check('''
          local w=require('hd2runtime/runtime/event_world')
          w.players=function() error('simulated unreadable state') end
          local a,why=aim.capture(world,{['968211C0033DCE64']=true})
          assert(a==nil and why=='aim_read_failed')
        ''')
