"""Map/deployment regression: real private avatar reader, synthetic game layout.

The avatar manager layout is Runtime's player_equipment domain; flag identities
1/84/86/114 are from C4 Quick Actions 1.13.1's avatar UI/pose guard. Lifecycle 3
is the existing Runtime spawned lifecycle. No game process or native call runs.
"""
import unittest
from homing_test_support import run
from test_homing_reticle import PRELUDE as HUD_PRELUDE

MODULES=('core/bytes','domains/player_equipment','domains/event_natives',
         'runtime/player_equipment','runtime/homing_visibility',
         'runtime/homing_reticle_style','runtime/homing_reticle')
PRELUDE=r'''
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/player_equipment');local AV=D.avatar
local mem={};local manager,buckets,descriptor=0x200000,0x300000,0x400000
local flags_address=manager+AV.flags
local function put(at,text)for i=1,#text do mem[at+i-1]=text:sub(i,i)end end
local function u32(n)return b.encode(n,'u32')end
local function pointer(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local function read(at,n)
 local out={};for i=0,n-1 do if not mem[at+i]then return nil end;out[#out+1]=mem[at+i]end
 return table.concat(out)
end
local players={{['local']=true,peer='local-peer',avatar=100,lifecycle=3}}
local healthy,owned,proof=true,true,true
local visibility_world={game=0x100000,key='synthetic-avatar-context',view={}}
local v=visibility_world.view
v.read=read;v.pointer=function(at)local bytes=read(at,8);return bytes and b.pointer(bytes,0)end
v.u32=function(at)local bytes=read(at,4);return bytes and b.u32(bytes,0)end
v.proves=function()return proof end
put(visibility_world.game+AV.global,pointer(manager))
put(manager+AV.hash,pointer(buckets)..u32(8)..u32(0)..u32(1))
put(buckets,string.rep('\0',64));put(buckets+(100%8)*8,u32(100)..u32(0))
put(manager+AV.descriptors,pointer(descriptor))
put(descriptor,u32(123)..u32(456)..u32(100)..u32(0)..u32(0x7fff)..u32(1))
local function flags(bits)
 local bytes={};for i=1,16 do bytes[i]=0 end
 for _,index in ipairs(bits)do local i=math.floor(index/8)+1;bytes[i]=bytes[i]+2^(index%8)end
 local out={};for i=1,16 do out[i]=string.char(bytes[i])end
 put(flags_address,table.concat(out))
end
flags({1})
-- Existing MOM UI stack: no escape screen, no cursor. These regressions must
-- not pass merely because a different menu or released Aim happened to hide it.
put(visibility_world.game+0x347ce28,pointer(0x500000))
put(0x500000+0x429c,string.rep('\0',24))
local W={open=function()return visibility_world end,
 players=function(_,avatars)assert(avatars==true);return players end,
 game_state=function()return{mission=true,host=true,mode_entity=99}end,
 entity_exists=function(_,entity)return entity==100 end,
 entity_state=function(_,entity)
  if entity~=100 then return nil end
  return{life=healthy and 0 or 2,descriptor={pointer=descriptor,entity=100,unit=200,owned=owned}}
 end,
 mul32=function(a,c)return a*c%4294967296 end}
package.preload['hd2runtime/runtime/event_world']=function()return W end
package.preload['hd2runtime/runtime/events']=function()return{}end
package.preload['hd2runtime/runtime/log']=function()return{emit=function()end}end
package.preload['hd2runtime/runtime/metrics']=function()return{count=function()end}end
package.preload['hd2runtime/runtime/scheduler']=function()return{}end
package.preload['hd2runtime/runtime/pelican_weapon']=function()return{}end
package.preload['hd2runtime/runtime/custom_weapons']=function()return{}end
package.preload['hd2runtime/runtime/windows_readonly']=function()error('native adapter forbidden')end
package.preload['hd2runtime/runtime/runtime_settings']=function()return{visible=function()return false end}end
package.preload['hd2runtime/runtime/homing_aim_state']=function()
 return{active=function()return true,'native_aim_action_2_8'end}
end
package.preload['hd2runtime/runtime/homing_drop_state']=package.preload['hd2runtime/runtime/homing_drop_state']or function()
 return{active=function()return false,'no_active_player_drop',{state='none',count=0}end}
end
stingray={Window={show_cursor=function()return false end}}
local Visibility=require('hd2runtime/runtime/homing_visibility')
'''


class VisibilityGateTests(unittest.TestCase):
    def check(self,body,hud=False):
        prefix=HUD_PRELUDE+PRELUDE if hud else PRELUDE
        self.assertEqual(run(prefix+body,MODULES),b'ok')

    def test_private_avatar_reader_uses_actual_layout_and_rejects_unknown_state(self):
        self.check('''
local equipment=require('hd2runtime/runtime/player_equipment')
flags({1,84,86,114})
local state=assert(equipment.avatar_flags(visibility_world,100))
assert(state.alive and state.tactical_map and state.weapon_menu and state.seated)
flags({1});state=assert(equipment.avatar_flags(visibility_world,100))
assert(state.alive and not state.tactical_map and not state.weapon_menu and not state.seated)
for i=0,15 do mem[flags_address+i]=nil end
assert(equipment.avatar_flags(visibility_world,100)==nil,'unreadable flags are not a closed map')
''')

    def test_tactical_map_and_weapon_menu_suppress_even_with_aim_true_and_no_cursor(self):
        self.check('''
assert(Visibility.blocked(visibility_world)==false)
for _,flag in ipairs({84,86})do
 flags({1,flag})
 assert(Visibility.blocked(visibility_world)==true,'avatar UI flag ignored while Aim is active')
 assert(Visibility.blocked(visibility_world,false)==true,'aim_only=false bypassed a map/menu gate')
 flags({1});assert(Visibility.blocked(visibility_world)==false)
end
''')

    def test_deployment_or_unproven_local_avatar_never_draws(self):
        self.check('''
assert(Visibility.blocked(visibility_world)==false)
for _,lifecycle in ipairs({0,1,2,4})do
 players[1].lifecycle=lifecycle
 assert(Visibility.blocked(visibility_world)==true,'non-spawned lifecycle accepted an active Aim input')
end
players[1].lifecycle=nil;assert(Visibility.blocked(visibility_world)==true)
players[1].lifecycle=3;healthy=false;assert(Visibility.blocked(visibility_world)==true)
healthy=true;owned=false;assert(Visibility.blocked(visibility_world)==true)
owned=true;flags({1,114});assert(Visibility.blocked(visibility_world)==true,'seated avatar is not on foot')
flags({});assert(Visibility.blocked(visibility_world)==true,'missing alive flag accepted')
flags({1});assert(Visibility.blocked(visibility_world)==false)
''')

    def test_unknown_flags_fail_closed_and_recover_without_a_latched_toggle(self):
        self.check('''
assert(Visibility.blocked(visibility_world)==false)
for i=0,15 do mem[flags_address+i]=nil end
assert(Visibility.blocked(visibility_world)==true,'unknown map/deployment context treated as gameplay')
flags({1});assert(Visibility.blocked(visibility_world)==false)
visibility_world.key='changed-build';proof=false
assert(Visibility.blocked(visibility_world)==true,'unproven flag layout accepted')
''')

    def test_frame_tick_clears_retained_ring_and_stock_markers_on_map_and_deployment(self):
        self.check('''
enable_stock_assets();S.Window={show_cursor=function()return false end};stingray=S
local h=Hud.new({view=View,style={marker_shape='vanilla'},
 blocked=function()return Visibility.blocked(visibility_world,false)end})
local s=snapshot();h:update(s)
assert(h:status().ring and h:status().marker_renderer=='vanilla_asset'and live_gui_count()==3)
flags({1,84});local created=calls.create;h:tick()
assert(live_gui_count()==0 and h:status().state=='suppressed','map left retained ring or stock markers visible')
h:update(s);assert(calls.create==created,'map recreated a suppressed stock HUD')
flags({1});h:update(s);assert(h:status().ring and live_gui_count()==3)
players[1].lifecycle=2;created=calls.create;h:tick()
assert(live_gui_count()==0 and h:status().state=='suppressed','deployment left retained HUD visible')
h:update(s);assert(calls.create==created)
players[1].lifecycle=3;h:update(s);assert(h:status().state=='drawing'and live_gui_count()==3)
h:shutdown();assert(live_gui_count()==0)
''',hud=True)
