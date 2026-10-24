import unittest
from homing_test_support import run

PRELUDE=r'''
local Los=require('hd2runtime/runtime/homing_los')

          world={key='proven-world'}
          origin={x=0,y=0,z=1}; target={x=0,y=10,z=1}
          ids={target_unit=300,avatar_unit=100,weapon_unit=200}
          calls=0
          result={abi_verified=true,world_verified=true,world_key=world.key,
                  complete=true,overflow=false,hits={}}
          reader=function(w,q)
            calls=calls+1; request=q; assert(w==world); return result
          end
          los=Los.new({read=reader})
          function query() return los:visible(world,origin,target,ids) end
          package.preload.ffi=function()error('FFI forbidden')end

'''

class LosTests(unittest.TestCase):
    def check(self,code):
        self.assertEqual(run(PRELUDE+code,('runtime/homing_los',)),b'ok')

    def test_without_reader_is_unknown_and_loads_no_ffi(self):
        self.check('''
          local value,why=Los.new():visible(world,origin,target,ids)
          assert(value==nil and why=='reader_unavailable');assert(package.loaded.ffi==nil)
        ''')

    def test_complete_no_hit_is_clear_and_normalizes_request(self):
        self.check('''
          local value,why= query();assert(value==true and why=='clear_no_hit')
          assert(request.distance==10 and request.direction.y==1 and request.direction.x==0)
          assert(request.origin~=origin and request.target~=target)
          assert(request.target_unit==300 and request.avatar_unit==100 and request.weapon_unit==200)
          assert(origin.y==0 and target.y==10 and calls==1)
        ''')

    def test_sort_ignores_owner_and_accepts_target_surface(self):
        self.check('''
          result.hits={{distance=9.5,unit=0},{distance=.1,unit=100},
            {distance=8,unit=300},{distance=.3,unit=200}}
          local first=result.hits[1]
          local value,why,detail=query()
          assert(value==true and why=='target_hit' and detail.hit_distance==8)
          assert(detail.hit_unit==300 and detail.ignored_owner_hits==2)
          assert(result.hits[1]==first, 'do not mutate reader result ordering')
        ''')

    def test_first_nonowner_obstruction_is_blocked(self):
        self.check('''
          result.hits={{distance=8,unit=300},{distance=5,unit=777},{distance=.2,unit=100}}
          local value,why,detail=query()
          assert(value==false and why=='occluded' and detail.hit_unit==777 and detail.hit_distance==5)
        ''')

    def test_geometry_unit_zero_is_not_treated_as_missing(self):
        self.check('''
          result.hits={{distance=5,unit=0}}
          local value,why=query();assert(value==false and why=='occluded')
        ''')

    def test_owner_only_complete_result_is_clear(self):
        self.check('''
          result.hits={{distance=1,unit=100},{distance=2,unit=200}}
          local value,why,detail=query()
          assert(value==true and why=='clear_owner_only' and detail.ignored_owner_hits==2)
        ''')

    def test_missing_abi_world_complete_or_overflow_is_unknown(self):
        self.check('''
          for _,name in ipairs({'abi_verified','world_verified','complete'})do
            result[name]=nil;assert(query()==nil);result[name]=true
          end
          result.overflow=true;assert(query()==nil);result.overflow=false
          result.overflow=nil;assert(query()==nil)
        ''')

    def test_wrong_world_and_world_change_during_query_are_unknown(self):
        self.check('''
          result.world_key='stale';assert(query()==nil);result.world_key=world.key
          los=Los.new({read=function()world.key='new';return result end})
          local value,why=query();assert(value==nil and why=='world_changed')
        ''')

    def test_bad_hits_including_later_records_do_not_become_clear(self):
        self.check('''
          for _,h in ipairs({{distance=-1,unit=300},{distance=0/0,unit=300},
             {distance=11,unit=300},{distance=2,unit=-1},{distance=2},
             {distance=2,unit=1.5},{distance=2,unit=4294967296}})do
            result.hits={{distance=1,unit=300},h};assert(query()==nil)
          end
          result.hits={[1]={distance=1,unit=300},[3]={distance=3,unit=0}};assert(query()==nil)
          result.hits={bad={distance=1,unit=300}};assert(query()==nil)
          result.hits={};for i=1,Los.MAX_HITS+1 do result.hits[i]={distance=1,unit=300}end
          assert(query()==nil)
        ''')

    def test_equal_target_and_other_hit_distances_are_unknown(self):
        self.check('''
          result.hits={{distance=8,unit=300},{distance=8,unit=777}}
          local value,why=query();assert(value==nil and why=='ambiguous_first_hit')
        ''')

    def test_invalid_input_never_calls_reader(self):
        self.check('''
          for _,v in ipairs({0/0,math.huge,100001})do origin.x=v;assert(query()==nil)end
          origin.x=0;target.y=0;assert(query()==nil)
          target.y=500;assert(query()==nil);target.y=10
          ids.target_unit=100;assert(query()==nil);ids.target_unit=300
          ids.weapon_unit=nil;assert(query()==nil);ids.weapon_unit=200
          world.key=nil;assert(query()==nil)
          assert(calls==0)
        ''')

    def test_reader_failures_and_unknown_shapes_stay_unknown(self):
        self.check('''
          los=Los.new({read=function()error('native guard refused')end})
          local value,why=query();assert(value==nil and why=='reader_error')
          los=Los.new({read=function()return nil,'budget_exhausted'end})
          local value,why=query();assert(value==nil and why=='budget_exhausted')
          los=Los.new({read=function()return true end});assert(query()==nil)
        ''')
