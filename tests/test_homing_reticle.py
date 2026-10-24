import ctypes,unittest
from homing_test_support import run,modules
from lua_offline import library,LUA_GLOBALSINDEX,_top_string

PRELUDE=r'''
local Hud=require('hd2runtime/runtime/homing_reticle')

calls={create=0,destroy=0,triangles=0,rects=0,rect_updates=0,texts=0,text_updates=0,temps=0}
guis={};next_id=0;live_worlds={'main','ui'};font_ready=true;fail_rect=false
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<100000 end
local function vector(...)local t={...};for _,v in ipairs(t)do assert(finite(v))end;return t end
S={Application={worlds=function()return live_worlds end,main_world=function()return'main'end,
can_get=function()return font_ready end},World={},Gui={},Vector2=vector,Vector3=vector,Color=vector,
Script={temp_count=function()return 99 end,set_temp_count=function(n)assert(n==99);calls.temps=calls.temps+1 end}}
S.World.create_screen_gui=function(world,mode,x,y)
 assert(world=='ui' and mode=='scale' and x==1 and y==1)
 calls.create=calls.create+1;local gui={world=world,rects={},texts={}};guis[#guis+1]=gui;return gui
end
S.World.destroy_gui=function(world,gui)
 local found=false;for _,w in pairs(live_worlds)do if w==world then found=true end end
 assert(found,'destroy on dead world');assert(not gui.dead);gui.dead=true;calls.destroy=calls.destroy+1
end
S.Gui.resolution=function()return 1920,1080 end
S.Gui.triangle=function(gui,a,b,c,layer,color)
 assert(not gui.dead and a[2]==0 and b[2]==0 and c[2]==0)
 assert(layer>=0 and layer<=1023);calls.triangles=calls.triangles+1
end
S.Gui.rect=function(gui,pos,size,color)
 if fail_rect then error('injected GUI failure')end
 assert(not gui.dead and size[1]>0 and size[2]>0)
 next_id=next_id+1;gui.rects[next_id]={pos=pos,size=size,color=color};calls.rects=calls.rects+1;return next_id
end
S.Gui.update_rect=function(gui,id,pos,size,color)
 assert(not gui.dead and gui.rects[id]);assert(size[1]>0 and size[2]>0)
 gui.rects[id]={pos=pos,size=size,color=color};calls.rect_updates=calls.rect_updates+1
end
S.Gui.destroy_rect=function(gui,id)assert(not gui.dead and gui.rects[id]);gui.rects[id]=nil end
S.Gui.text=function(gui,text,font,size,material,pos,color)
 assert(font_ready and not gui.dead);assert(font=='core/performance_hud/monaco' and material==font)
 next_id=next_id+1;gui.texts[next_id]={text=text,pos=pos,color=color};calls.texts=calls.texts+1;return next_id
end
S.Gui.update_text=function(gui,id,text,font,size,material,pos,color)
 assert(font_ready and not gui.dead and gui.texts[id]);gui.texts[id]={text=text,pos=pos,color=color}
 calls.text_updates=calls.text_updates+1
end
S.Gui.destroy_text=function(gui,id)assert(not gui.dead and gui.texts[id]);gui.texts[id]=nil end
View={project=function(frame,target)
 if target.behind then return nil end
 return {x=target.x,y=target.y,depth=target.z}
end,radius=function(frame,angle)return frame.radius or 120 end}
frame={width=1920,height=1080,world='main',ui_world='ui',sr=S}
function snapshot()return {visible=true,frame=frame,session='one',half_angle=12,max_targets=3,mode='multi',
locked={{key='b',x=1200,y=600,z=10}},acquiring={{key='a',x=500,y=300,z=10,progress=.25}}}end
logs={};function make()return Hud.new({view=View,log=function(text)logs[#logs+1]=text end})end
function text_present(wanted)
 for _,gui in ipairs(guis)do if not gui.dead then for _,item in pairs(gui.texts)do
  if item.text:find(wanted,1,true)then return true end end end end
 return false
end
function live_gui_count()local n=0;for _,gui in ipairs(guis)do if not gui.dead then n=n+1 end end;return n end
function enable_stock_assets()
 stock_loaded=true;calls.bitmaps,calls.bitmap_updates,calls.texture_binds=0,0,0
 S.IdString64={from_hex=function(hex)return'hash:'..hex end}
 S.Material={set_texture=function(material,slot,texture)
  assert(not material.gui.dead and slot=='hash:3aa8b87e00000000' and texture=='hash:f9a3f22a93eedcbd')
  calls.texture_binds=calls.texture_binds+1
 end}
 S.Application.can_get=function(kind,name)
  if name=='hash:5af18dfb697cfef2'or name=='hash:f9a3f22a93eedcbd'then return stock_loaded end
  return font_ready
 end
 S.Gui.material=function(gui,name)
  assert(not gui.dead and name=='hash:5af18dfb697cfef2')
  assert(gui.bitmaps and next(gui.bitmaps),'material instance requires a bitmap of that material first')
  return{gui=gui}
 end
 S.Quaternion={axis_angle=function(axis,angle)
  assert(axis[1]==0 and axis[2]==1 and axis[3]==0);return{angle=angle}
 end}
 S.Matrix4x4={from_quaternion_position=function(rotation,position)return{rotation=rotation,position=position}end}
 local function bitmap(gui,id,material,uv0,uv1,pose,pos,layer,size,color)
  assert(not gui.dead and material=='hash:5af18dfb697cfef2')
  assert(uv0[1]==.5712890625 and uv0[2]==.0078125)
  assert(uv1[1]==.6025390625 and uv1[2]==.0703125)
  assert(size[1]==48 and size[2]==48 and layer>=0 and layer<=1023)
  assert(pos[1]==0 and pos[2]==0 and pos[3]==0)
  gui.bitmaps=gui.bitmaps or{}
  gui.bitmaps[id]={pose=pose,color=color}
 end
 S.Gui.bitmap_3d_uv=function(gui,...)
  next_id=next_id+1;bitmap(gui,next_id,...);calls.bitmaps=calls.bitmaps+1;return next_id
 end
 S.Gui.update_bitmap_3d_uv=function(gui,id,...)
  assert(gui.bitmaps and gui.bitmaps[id]);bitmap(gui,id,...);calls.bitmap_updates=calls.bitmap_updates+1
 end
end

'''

class ReticleTests(unittest.TestCase):
    def test_vanilla_defaults_show_only_marker_art_without_mod_decorations(self):
        self.check('''
for _,assets in ipairs({false,true})do
 if assets then enable_stock_assets()end
 local previous_rects=calls.rects
 local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false}})
 h:update(snapshot())
 assert(not text_present('LOCK')and not text_present('ACQ')and not text_present('LOS'),
  'Vanilla defaults must not include mod labels')
 if assets then
  assert(calls.rects==previous_rects,'stock marker mode must not add bars or numbers')
  assert(calls.bitmaps==6)
 else
  for _,gui in ipairs(guis)do if not gui.dead then
   local n=0;for _ in pairs(gui.rects)do n=n+1 end
   assert(n==96,'fallback should contain only three chevrons per target')
  end end
 end
 h:shutdown()
end
local decorated=Hud.validate_style({marker_shape='vanilla',show_numbers=true})
assert(decorated.show_numbers==true and decorated.show_labels==false)
local standard=Hud.validate_style({marker_shape='corners'})
assert(standard.show_labels and standard.show_numbers and standard.show_progress and standard.show_los)
''')

    def test_vanilla_null_lightuserdata_material_never_reaches_texture_setter(self):
        script=modules(('runtime/homing_reticle_style','runtime/homing_reticle'))+PRELUDE+'''
assert(type(NULL_MATERIAL)=='userdata' and tostring(NULL_MATERIAL):find('NULL',1,true))
enable_stock_assets()
local setter_calls=0
S.Gui.material=function()return NULL_MATERIAL end
S.Material.set_texture=function()setter_calls=setter_calls+1 end
local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false,show_labels=false,
 show_numbers=false,show_progress=false,show_los=false}})
local s=snapshot();s.acquiring={};h:update(s)
assert(setter_calls==0,'a native NULL lightuserdata must never reach Material.set_texture')
assert(h:status().marker_renderer=='vanilla_geometry' and h:status().renderer_reason=='marker_setup_failed')
assert(live_gui_count()==1,'the failed stock GUI is destroyed before fallback')
h:shutdown();assert(live_gui_count()==0)
return 'ok'
'''
        lib=library();lib.lua_pushlightuserdata.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        lib.lua_setfield.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_char_p]
        state=lib.luaL_newstate()
        self.assertTrue(state)
        try:
            lib.luaL_openlibs(state)
            lib.lua_pushlightuserdata(state,None)
            lib.lua_setfield(state,LUA_GLOBALSINDEX,b'NULL_MATERIAL')
            source=script.encode()
            status=lib.luaL_loadbuffer(state,source,len(source),b'@null-material-fixture')
            if status==0:status=lib.lua_pcall(state,0,1,0)
            result=_top_string(lib,state)
            self.assertEqual(status,0,result.decode('utf-8','replace'))
            self.assertEqual(result,b'ok')
        finally:
            lib.lua_close(state)

    def test_vanilla_uses_resident_stock_sprite_with_guarded_exact_bindings(self):
        self.check('''
enable_stock_assets()
local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false,show_labels=false,
 show_numbers=false,show_progress=false,show_los=false}})
local s=snapshot();h:update(s)
assert(h:status().marker_renderer=='vanilla_asset' and not h:status().renderer_reason)
assert(calls.bitmaps==6 and calls.texture_binds==1 and calls.rects==0 and live_gui_count()==2)
local created=calls.create;h:update(s)
assert(calls.create==created and calls.bitmaps==6 and calls.bitmap_updates==0,'unchanged stock quads are retained')
s.acquiring[1].progress=.5;h:update(s)
assert(calls.bitmap_updates==3 and calls.bitmaps==6 and calls.create==created,'progress updates only that target')
local seen=0
for _,gui in ipairs(guis)do if not gui.dead then for _,item in pairs(gui.bitmaps or{})do
 assert(type(item.pose.rotation.angle)=='number' and item.pose.position[2]==0)
 seen=seen+1
end end end
assert(seen==6 and calls.temps==3,'stock poses are contained by the temporary scope')
h:shutdown();assert(live_gui_count()==0)
''')

    def test_vanilla_stock_unload_and_target_removal_clear_quads_before_fallback(self):
        self.check('''
enable_stock_assets()
local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false,show_labels=false,
 show_numbers=false,show_progress=false,show_los=false}})
local s=snapshot();h:update(s)
assert(h:status().marker_renderer=='vanilla_asset')
s.acquiring={};h:update(s)
assert(calls.destroy==1 and calls.bitmaps==9,'target membership replaces only stock GUI without ghost quads')
stock_loaded=false;h:update(s)
assert(h:status().marker_renderer=='vanilla_geometry' and h:status().renderer_reason=='material_not_loaded')
assert(calls.destroy==2 and calls.rects==48 and live_gui_count()==1)
stock_loaded=true;h:update(s)
assert(h:status().marker_renderer=='vanilla_asset' and live_gui_count()==2)
for _,gui in ipairs(guis)do if not gui.dead then assert(next(gui.rects)==nil,'geometry fallback is removed')end end
live_worlds={'main'};h:update(s);h:shutdown()
assert(calls.destroy==2,'removed worlds must never receive native GUI destruction')
''')

    def test_vanilla_texture_residency_and_setup_are_required_independently(self):
        self.check('''
enable_stock_assets()
local can_get=S.Application.can_get
S.Application.can_get=function(kind,name)
 if kind=='texture'and name=='hash:f9a3f22a93eedcbd'then return false end
 return can_get(kind,name)
end
local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false,show_labels=false,
 show_numbers=false,show_progress=false,show_los=false}})
local s=snapshot();s.acquiring={};h:update(s)
assert(h:status().marker_renderer=='vanilla_geometry' and h:status().renderer_reason=='texture_not_loaded')
assert(calls.bitmaps==0 and calls.texture_binds==0,'material residency does not prove texture residency')
S.Application.can_get=can_get
local bind=S.Material.set_texture
S.Material.set_texture=function()error('asset bind unavailable')end
h:update(s)
assert(h:status().marker_renderer=='vanilla_geometry' and h:status().renderer_reason=='marker_setup_failed')
assert(calls.bitmaps==3 and live_gui_count()==1,'seeded stock GUI is destroyed before geometry fallback')
S.Material.set_texture=bind;h:update(s)
assert(h:status().marker_renderer=='vanilla_asset' and calls.bitmaps==6)
h:shutdown();assert(live_gui_count()==0)
''')

    def test_vanilla_replica_spins_contracts_and_locks_without_sprite_assets(self):
        self.check('''
font_ready=false
local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false,show_labels=false,
 show_numbers=false,show_progress=false,show_los=false}})
local s=snapshot();s.locked={};s.acquiring={{key='a',x=500,y=300,z=10,progress=0}}
local start_x,start_y
local function radius()
 local furthest=0
 for _,gui in ipairs(guis)do if not gui.dead then for _,item in pairs(gui.rects)do
  local dx,dy=item.pos[1]+item.size[1]/2-500,item.pos[2]+item.size[2]/2-300
  furthest=math.max(furthest,math.sqrt(dx*dx+dy*dy))
 end end end
 return furthest
end
h:update(s);local outer=radius()
assert(h:status().state=='drawing' and calls.rects==48 and calls.triangles==0 and calls.texts==0)
assert(h:status().marker_renderer=='vanilla_geometry' and h:status().renderer_reason=='marker_api_missing')
start_x,start_y=guis[1].rects[1].pos[1],guis[1].rects[1].pos[2]
assert(start_x<500 and start_y>300,'first chevron starts above its target')
local created=calls.rects
s.acquiring[1].progress=.25;h:update(s)
assert(calls.rects==created and calls.rect_updates>0 and radius()<outer,'acquisition rotates and contracts retained marks')
assert(guis[1].rects[1].pos[1]>500 and guis[1].rects[1].pos[2]<start_y,'quarter progress rotates the first chevron right')
s.locked=s.acquiring;s.acquiring={};h:update(s)
assert(h:status().locked==1 and h:status().acquiring==0 and radius()<outer/2)
for _,gui in ipairs(guis)do if not gui.dead then for _,item in pairs(gui.rects)do
 assert(item.color[2]==64 and item.color[3]==255 and item.color[4]==96,'locked style colour is preserved')
end end end
assert(calls.create==1 and calls.destroy==0,'progress must not recreate the marker GUI')
local updates=calls.rect_updates;h:update(s)
assert(calls.rect_updates==updates,'an unchanged locked frame makes no geometry update')
assert(calls.temps==4,'each render restores the temporary ring')
s.locked={};h:update(s);assert(h:status().markers==0)
for _,gui in ipairs(guis)do if not gui.dead then assert(next(gui.rects)==nil)end end
h:shutdown();assert(live_gui_count()==0)
''')

    def test_vanilla_labels_and_progress_stay_outside_the_orbit(self):
        self.check('''
local h=Hud.new({view=View,style={marker_shape='vanilla',ring=false,show_numbers=false,show_los=false,
 show_labels=true,show_progress=true}})
local s=snapshot();s.locked={};s.acquiring={{key='a',x=500,y=300,z=10,progress=0}}
h:update(s)
local label_y
for _,item in pairs(guis[1].texts)do if item.text:find('ACQ',1,true)then label_y=item.pos[2]end end
assert(label_y and label_y>337,'the acquiring label must clear the 28px outer chevrons')
''')

    def test_vanilla_replica_preserves_multi_target_numbers_los_and_menu_gate(self):
        self.check('''
local blocked=false
local h=Hud.new({view=View,style={marker_shape='vanilla',show_labels=true,show_numbers=true,
 show_progress=true,show_los=true},blocked=function()return blocked,'not_aiming'end})
local s=snapshot();s.locked={};s.acquiring={};s.max_targets=6
for i=1,6 do s.locked[i]={key='t'..i,x=200+i*200,y=400,z=10,los=i==1 and'blocked'or'clear'}end
h:update(s)
assert(h:status().markers==6 and h:status().locked==6 and calls.rects<=384 and calls.texts==12)
assert(text_present('LOS BLOCKED') and text_present('LOCK'))
local numbers=h:status().numbers
s.locked[1].x=450;h:update(s)
assert(h:status().numbers.t1==numbers.t1 and calls.create==2 and calls.destroy==0)
blocked=true;h:tick();assert(live_gui_count()==0 and h:status().reason=='not_aiming')
blocked=false;h:tick();assert(live_gui_count()==0,'resume needs fresh observations')
h:update(s);assert(h:status().markers==6 and live_gui_count()==2)
''')

    def test_style_bounds_colours_shapes_and_two_owners_do_not_interfere(self):
        self.check('''
local a=Hud.new({view=View,style={marker_shape='cross',marker_size=20,ring_color='#FF000080',
 ring_width=4,ring_segments=24,show_labels=false,show_numbers=false,show_los=false}})
local s=snapshot();a:update(s)
assert(calls.triangles==48 and calls.texts==0)
local b=Hud.new({view=View,style={marker_shape='box',locked_color={0,255,0}}})
b:update(s);assert(live_gui_count()==4 and a:status().state=='drawing')
a:shutdown();assert(live_gui_count()==2 and b:status().state=='drawing')
for _,bad in ipairs({{marker_shape='triangle'},{ring_width=0},{ring_segments=129},
 {marker_size=0/0},{locked_color='#xyz'},{show_labels=1},{unknown_key=1}})do
 assert(not pcall(Hud.new,{view=View,style=bad}),'invalid style accepted')
end
assert(b:status().state=='drawing')
''')

    def check(self,body):self.assertEqual(run(PRELUDE+body,('runtime/homing_reticle_style','runtime/homing_reticle')),b'ok')

    def test_idle_invisible_snapshot_does_not_emit_two_log_lines_every_frame(self):
        self.check('''
local h=Hud.new({view=View,log=function(text)logs[#logs+1]=text end,
 blocked=function()return true,'not_aiming'end})
local s=snapshot();s.visible=false
for i=1,30 do h:tick();h:update(s)end
assert(#logs<=2,'hidden/suppressed status oscillated while nothing was drawn')
assert(live_gui_count()==0)
''')

    def test_los_label_is_independent_of_locked_state(self):
        self.check('''
local h=make();local s=snapshot();s.locked[1].los='blocked';h:update(s)
assert(text_present('LOCK') and text_present('LOS BLOCKED'))
s.locked[1].los='clear';h:update(s);assert(text_present('LOS CLEAR') and not text_present('LOS BLOCKED'))
s.locked[1].los='unknown';h:update(s);assert(text_present('LOS ?') and not text_present('LOS CLEAR'))
''')

    def test_menu_open_hides_existing_gui_without_waiting_for_engine_observation(self):
        self.check('''
local blocked=false
local h=Hud.new({view=View,blocked=function()return blocked,'escape_menu'end})
local s=snapshot();h:update(s);assert(live_gui_count()==2)
blocked=true;h:tick();assert(live_gui_count()==0 and h:status().reason=='escape_menu')
h:update(s);assert(live_gui_count()==0)
blocked=false;h:tick();assert(live_gui_count()==0,'do not redraw an old camera frame')
h:update(s);assert(live_gui_count()==2)
''')

    def test_ring_and_target_markers_are_retained_and_snapshot_is_not_modified(self):
        self.check('''
local h=make();local s=snapshot();h:update(s,.016)
assert(h:status().state=='drawing' and h:status().markers==2)
assert(calls.create==2 and calls.triangles==192 and calls.rects>16)
assert(text_present('LOCK') and text_present('25%'))
local rc,tc=calls.rects,calls.texts;local count=calls.temps
h:update(s,.016)
assert(calls.create==2 and calls.triangles==192 and calls.rects==rc and calls.texts==tc)
assert(calls.rect_updates==0 and calls.text_updates==0 and calls.temps>count)
assert(s.acquiring[1].progress==.25 and s.acquiring[1].key=='a' and s.locked[1].key=='b')
''')

    def test_promotion_and_motion_keep_numbers_and_gui_handles(self):
        self.check('''
local h=make();local s=snapshot();h:update(s,.016)
local numbers=h:status().numbers;local a,b=numbers.a,numbers.b
assert(a~=b and a>=1 and b<=6)
s.locked={{key='a',x=510,y=320,z=10},{key='b',x=1190,y=600,z=10}};s.acquiring={}
h:update(s,.016)
assert(calls.create==2 and calls.destroy==0 and calls.triangles==192)
assert(h:status().numbers.a==a and h:status().numbers.b==b and h:status().locked==2)
assert(calls.rect_updates>0 and text_present('LOCK') and not text_present('25%'))
''')

    def test_radius_change_rebuilds_only_ring_and_resolution_rebuilds_both(self):
        self.check('''
local h=make();local s=snapshot();h:update(s,.016)
frame.radius=140;h:update(s,.016)
assert(calls.create==3 and calls.destroy==1 and calls.triangles==384)
frame.radius=140.1;h:update(s,.016);assert(calls.create==3)
frame.width=2560;frame.height=1440;h:update(s,.016)
assert(calls.create==5 and calls.destroy==3 and h:status().markers==2)
''')

    def test_hidden_shutdown_and_session_changes_clear_owned_primitives(self):
        self.check('''
local h=make();local s=snapshot();h:update(s,.016)
s.session='two';h:update(s,.016);assert(calls.destroy==2 and calls.create==4)
s.visible=false;h:update(s,.016)
assert(calls.destroy==4 and live_gui_count()==0 and h:status().state=='hidden')
s.visible=true;h:update(s,.016);assert(live_gui_count()==2)
h:shutdown();assert(live_gui_count()==0 and h:status().state=='stopped')
local count=calls.create;h:update(s,.016);assert(calls.create==count)
''')

    def test_dead_world_is_never_passed_to_native_destroy(self):
        self.check('''
local h=make();local s=snapshot();h:update(s,.016)
live_worlds={'main'};h:update(s,.016)
assert(calls.destroy==0 and h:status().state=='unavailable')
h:shutdown();assert(calls.destroy==0)
''')

    def test_ui_world_must_be_distinct_and_camera_projection_uses_bottom_origin(self):
        self.check('''
local h=make();local s=snapshot();s.locked={};h:update(s,.016)
for _,gui in ipairs(guis)do if not gui.dead then for _,item in pairs(gui.rects)do
 assert(item.pos[2]>270 and item.pos[2]<340,'unexpected top-origin conversion')
end end end
frame.ui_world='main';h:update(s,.016)
assert(h:status().state=='unavailable' and calls.create==2 and live_gui_count()==0)
''')

    def test_bad_geometry_and_offscreen_targets_are_never_submitted(self):
        self.check('''
local h=make();local s=snapshot()
s.locked={{key='nan',x=0/0,y=100,z=10},{key='left',x=-100,y=100,z=10},
 {key='behind',x=100,y=100,z=-1},{key='far',x=2000,y=400,z=10}}
s.acquiring={};h:update(s,.016)
assert(h:status().markers==0 and calls.rects==0 and calls.texts==0)
frame.width=0/0;h:update(s,.016)
assert(h:status().state=='unavailable')
''')

    def test_font_unavailable_keeps_numbered_geometry_and_progress_without_font_calls(self):
        self.check('''
font_ready=false;local h=make();local s=snapshot();h:update(s,.016)
assert(h:status().markers==2 and not h:status().text_supported)
assert(h:status().reason=='font_unavailable' and calls.texts==0 and calls.rects>16)
local n=h:status().numbers;assert(n.a and n.b and n.a~=n.b)
font_ready=true;h:update(s,.016);assert(calls.create==2 and calls.texts==4)
font_ready=false;h:update(s,.016);assert(not text_present('LOCK'))
''')

    def test_six_target_limit_duplicates_and_retired_number_reuse_are_bounded(self):
        self.check('''
local h=make();local s=snapshot();s.locked={};s.acquiring={};s.max_targets=6
for i=1,10 do s.locked[i]={key='t'..i,x=100+i*50,y=100,z=10}end
h:update(s,.016);assert(h:status().markers==6)
local old=h:status().numbers
s.locked={{key='t2',x=200,y=100,z=10},{key='t2',x=200,y=100,z=10},
 {key='new',x=300,y=100,z=10}};h:update(s,.016)
assert(h:status().markers==2 and h:status().numbers.t2==old.t2)
assert(h:status().numbers.new and h:status().numbers.t1==nil)
''')
