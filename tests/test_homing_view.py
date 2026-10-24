import unittest
from homing_test_support import run

PRELUDE=r'''
local view=require('hd2runtime/runtime/homing_view')

          function vec(x,y,z) return {x=x,y=y,z=z} end
          local function ctor(_,x,y,z) return vec(x,y,z) end
          local V=setmetatable({x=function(v)return v.x end,y=function(v)return v.y end,
                               z=function(v)return v.z end},{__call=ctor})
          main={name='mission'}; ui={name='ui'}; worlds={main,ui}; width=1920;height=1080
          pose={position=vec(0,0,0),forward=vec(0,1,0)}
          cam={position=vec(0,0,0),forward=vec(0,1,0),right=vec(1,0,0),up=vec(0,0,1),fov=math.pi/3}
          unit={alive=true,cameras={cam}}; units={unit}; projections=0; scans=0
          stingray={Application={main_world=function()return main end,worlds=function()return worlds end},
            Script={temp_count=function()return 128 end,set_temp_count=function(n)assert(n==128)end},
            World={units=function(w)assert(w==main);scans=scans+1;return units end,
                   debug_camera_pose=function(w)assert(w==main);return pose end},
            Unit={alive=function(u)return u.alive end,num_cameras=function(u)return #u.cameras end,
                  camera=function(u,n)return u.cameras[n]end},
            Matrix4x4={translation=function(p)return p.position end,forward=function(p)return p.forward end},
            Vector3=V,Vector2=function(x,y)return{x=x,y=y}end,
            Gui={resolution=function()return width,height end},
            Camera={world_position=function(c)return c.position end,vertical_fov=function(c)return c.fov end,
              world_to_screen=function(c,p,unused,size)
                projections=projections+1;assert(unused==nil)
                local dx,dy,dz=p.x-c.position.x,p.y-c.position.y,p.z-c.position.z
                local d=dx*c.forward.x+dy*c.forward.y+dz*c.forward.z
                if d<=0 then return vec(0/0,0/0,0)end
                local k=(size.y/2)/math.tan(c.fov/2)
                return vec(size.x/2+k*(dx*c.right.x+dy*c.right.y+dz*c.right.z)/d+(c.slip or 0),
                           size.y/2+k*(dx*c.up.x+dy*c.up.y+dz*c.up.z)/d,d)
              end}}
          package.preload.ffi=function()error('FFI forbidden')end

'''

class ViewTests(unittest.TestCase):
    def check(self,code):
        self.assertEqual(run(PRELUDE+code,('runtime/homing_view',)),b'ok')

    def test_capture_uses_actual_camera_resolution_and_fov(self):
        self.check('''
          local f=assert(view.capture())
          assert(f.world==main and f.ui_world==ui and f.sr==stingray and f.camera==cam)
          assert(f.width==1920 and f.height==1080 and f.vertical_fov==cam.fov)
          assert(f.forward.y==1 and f.origin.x==0 and f.aim_basis=='render_camera')
          assert(package.loaded.ffi==nil)
        ''')

    def test_projection_has_bottom_origin_and_symmetric_radius(self):
        self.check('''
          local f=assert(view.capture());local r=assert(view.radius(f,12))
          local a=math.tan(math.rad(12))*10
          local left=assert(view.project(f,vec(-a,10,0)))
          local right=assert(view.project(f,vec(a,10,0)))
          local up=assert(view.project(f,vec(0,10,a)))
          local down=assert(view.project(f,vec(0,10,-a)))
          assert(math.abs(right.x-960-r)<1e-7 and math.abs(960-left.x-r)<1e-7)
          assert(math.abs(up.y-540-r)<1e-7 and math.abs(540-down.y-r)<1e-7)
          assert(left.depth==10)
        ''')

    def test_scope_fov_and_resolution_recompute_circle(self):
        self.check('''
          local r=view.radius(assert(view.capture()),10)
          cam.fov=math.pi/6
          local zoom=view.radius(assert(view.capture()),10)
          assert(zoom>r)
          width=3840;height=2160
          assert(math.abs(view.radius(assert(view.capture()),10)-zoom*2)<1e-7)
        ''')

    def test_missing_or_invalid_fov_has_no_fallback(self):
        self.check('''
          cam.fov=nil;assert(view.capture()==nil)
          cam.fov=0/0;assert(view.capture()==nil)
          cam.fov=math.pi;assert(view.capture()==nil)
        ''')

    def test_misaligned_camera_axis_is_not_recentered(self):
        self.check('''
          cam.slip=20;local f,why=view.capture()
          assert(f==nil and why=='camera_not_found')
        ''')

    def test_two_equivalent_cameras_are_ambiguous(self):
        self.check('''
          local second={};for k,v in pairs(cam)do second[k]=v end
          unit.cameras={cam,second};local f,why=view.capture()
          assert(f==nil and why=='camera_ambiguous')
        ''')

    def test_behind_and_invalid_points_never_call_projection(self):
        self.check('''
          local f=assert(view.capture());local before=projections
          assert(view.project(f,vec(0,-10,0))==nil)
          assert(view.project(f,vec(0,0,0))==nil)
          assert(view.project(f,vec(0/0,10,0))==nil)
          assert(view.project(f,vec(math.huge,10,0))==nil)
          assert(projections==before)
        ''')

    def test_stale_world_and_destroyed_camera_are_not_projected(self):
        self.check('''
          local f=assert(view.capture());local before=projections
          worlds={ui};assert(view.project(f,vec(0,10,0))==nil);assert(projections==before)
          worlds={main,ui};unit.alive=false
          assert(view.project(f,vec(0,10,0))==nil);assert(projections==before)
        ''')

    def test_unavailable_apis_and_invalid_angles_return_unknown(self):
        self.check('''
          local f=assert(view.capture())
          for _,a in ipairs({-1,90,180,0/0,math.huge})do assert(view.radius(f,a)==nil)end
          assert(view.radius(f,0)==0)
          stingray.Camera.world_to_screen=nil;assert(view.capture()==nil)
          stingray=nil;assert(view.capture()==nil)
        ''')

    def test_ambiguous_ui_world_does_not_select_arbitrary_world(self):
        self.check('''
          worlds={main,ui,{name='another'}}
          local f=assert(view.capture());assert(f.ui_world==nil and f.ui_reason=='ui_world_ambiguous')
        ''')

    def test_offscreen_points_are_omitted_without_center_fallback(self):
        self.check('''
          local f=assert(view.capture())
          assert(view.project(f,vec(100,1,0))==nil)
        ''')

    def test_temporary_vector_ring_is_restored_on_success_and_error(self):
        self.check('''
          local restored={}
          stingray.Script={temp_count=function()return 128 end,
            set_temp_count=function(n)restored[#restored+1]=n end}
          local f=assert(view.capture());assert(restored[1]==128)
          assert(view.project(f,vec(0,10,0)));assert(restored[2]==128)
          stingray.World.debug_camera_pose=function()error('simulated unavailable')end
          assert(view.capture()==nil);assert(restored[3]==128)
        ''')

    def test_proven_runtime_ui_world_resolves_multiple_nonmain_worlds(self):
        self.check('''
          local other={name='effects'};worlds={main,other,ui}
          local proven={key='proven_event_world'}
          package.preload['hd2runtime/runtime/stratagem_slot_overlay']=function()
            return{ui_world=function(w)assert(w==proven);return ui end}
          end
          local f=assert(view.capture(proven))
          assert(f.ui_world==ui and f.ui_source=='runtime_ui_world')
        ''')

    def test_unavailable_runtime_ui_query_uses_only_unique_nonmain(self):
        self.check('''
          package.preload['hd2runtime/runtime/stratagem_slot_overlay']=function()error('not bundled')end
          local f=assert(view.capture({key='proven'}))
          assert(f.ui_world==ui and f.ui_source=='sole_nonmain_reference')
          worlds={main,ui,{}};f=assert(view.capture({key='proven'}))
          assert(f.ui_world==nil and f.ui_reason=='ui_world_ambiguous')
        ''')

    def test_missing_temporary_api_never_allocates_or_reads_camera(self):
        self.check('''
          local f=assert(view.capture());local before=projections;local before_scans=scans
          stingray.Script=nil
          local frame,why=view.capture();assert(frame==nil and why=='temporary_api_missing')
          assert(view.project(f,vec(0,10,0))==nil)
          assert(projections==before and scans==before_scans)
          stingray.Script={temp_count=function()return 128 end}
          assert(view.capture()==nil and projections==before and scans==before_scans)
        ''')

    def test_invalid_temporary_mark_stops_before_camera_calls(self):
        self.check('''
          for _,n in ipairs({-1,1048576,1.5,0/0,math.huge})do
            stingray.Script.temp_count=function()return n end
            local f,why=view.capture();assert(f==nil and why=='temporary_mark_invalid')
          end
          assert(scans==0 and projections==0)
          stingray.Script.temp_count=function()error('unavailable')end
          assert(view.capture()==nil and scans==0 and projections==0)
        ''')

    def test_valid_camera_cache_avoids_reenumerating_world_every_capture(self):
        self.check('''
          assert(view.capture());assert(scans==1)
          for i=1,29 do assert(view.capture())end
          assert(scans==1)
          assert(view.capture());assert(scans==2)
        ''')

    def test_invalid_cached_camera_forces_immediate_rediscovery(self):
        self.check('''
          assert(view.capture());assert(scans==1)
          local second={};for k,v in pairs(cam)do second[k]=v end
          cam.slip=20;units[2]={alive=true,cameras={second}}
          local f=assert(view.capture())
          assert(f.camera==second and scans==2)
        ''')

    def test_scope_change_rescans_and_rejects_new_ambiguous_camera(self):
        self.check('''
          assert(view.capture());assert(scans==1)
          cam.fov=math.pi/6
          local second={};for k,v in pairs(cam)do second[k]=v end
          units[2]={alive=true,cameras={second}}
          local f,why=view.capture()
          assert(f==nil and why=='camera_ambiguous' and scans==2)
        ''')

    def test_added_camera_in_cached_unit_is_not_ignored(self):
        self.check('''
          assert(view.capture());assert(scans==1)
          local second={};for k,v in pairs(cam)do second[k]=v end
          unit.cameras[2]=second
          local f,why=view.capture()
          assert(f==nil and why=='camera_ambiguous' and scans==2)
        ''')

    def test_failed_discovery_backs_off_with_a_large_world(self):
        self.check('''
          units={};for i=1,1001 do units[i]={alive=true,cameras={}}end
          for i=1,30 do
            local f,why=view.capture();assert(f==nil and why=='camera_not_found')
          end
          assert(scans==1)
          assert(view.capture()==nil);assert(scans==2)
        ''')

    def test_success_invalidates_immediately_then_failure_backs_off(self):
        self.check('''
          assert(view.capture());assert(scans==1)
          cam.slip=20
          local f,why=view.capture();assert(f==nil and why=='camera_not_found' and scans==2)
          for i=1,29 do assert(view.capture()==nil)end
          assert(scans==2)
          assert(view.capture()==nil);assert(scans==3)
        ''')

    def test_failure_backoff_does_not_cross_resolution_or_world(self):
        self.check('''
          cam.slip=20;assert(view.capture()==nil);assert(scans==1)
          width=1280;height=720;assert(view.capture()==nil);assert(scans==2)
          main={name='new mission'};worlds={main,ui}
          assert(view.capture()==nil);assert(scans==3)
        ''')
