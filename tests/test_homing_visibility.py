import unittest
from homing_test_support import run

PRELUDE=r'''

local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
stack={0,0,0,0,0};depth=0;broken=false;reads=0
world={game=0x100000,key='proven',view={
 pointer=function(p)assert(p==world.game+0x347ce28);return 0x10000000 end,
 read=function(p,n)
  reads=reads+1;assert(p==0x10000000+0x429c and n==24)
  if broken then return nil end
  local s='';for i=1,5 do s=s..u32(stack[i])end;return s..u32(depth)
 end}}
package.preload['hd2runtime/runtime/event_world']=function()return {
 open=function()return world end,game_state=function()return{mission=true}end,
 players=function()return{{['local']=true,avatar=100,lifecycle=3}}end,
 entity_state=function()return{life=0,descriptor={owned=true}}end}end
package.preload['hd2runtime/runtime/player_equipment']=function()return{
 avatar_flags=function()return{alive=true,seated=false,tactical_map=false,weapon_menu=false}end}end
package.preload['hd2runtime/runtime/homing_drop_state']=function()return{
 active=function()return false,'no_active_player_drop',{state='none',count=0}end}end
aiming=true
package.preload['hd2runtime/runtime/homing_aim_state']=function()return {active=function()return aiming,'aim_state_unavailable'end}end
runtime_open=false
package.preload['hd2runtime/runtime/runtime_settings']=function()return {visible=function()return runtime_open end}end
stingray={Window={show_cursor=function()return false end}}

local Visibility=require('hd2runtime/runtime/homing_visibility')
'''

class VisibilityTests(unittest.TestCase):
    def check(self,code):
        self.assertEqual(run(PRELUDE+code,('runtime/homing_visibility',)),b'ok')

    def test_native_aim_release_unknown_and_reactivation_gate_without_latching(self):
        self.check('''
assert(Visibility.blocked()==false)
aiming=false;local hidden,why=Visibility.blocked();assert(hidden and why=='not_aiming')
aiming=nil;hidden,why=Visibility.blocked();assert(hidden and why=='aim_state_unavailable')
aiming=true;assert(Visibility.blocked()==false)
stack[1]=1;depth=1;assert(Visibility.blocked()==true)
depth=0;assert(Visibility.blocked()==false)
''')

    def test_escape_on_top_or_covered_suppresses_without_toggling_guess(self):
        self.check('''
assert(Visibility.blocked()==false)
stack[1]=1;depth=1;local hidden,why=Visibility.blocked();assert(hidden and why=='escape_menu')
stack[2]=4;depth=2;assert(Visibility.blocked()==true)
depth=0;assert(Visibility.blocked()==false)
''')

    def test_invalid_or_unreadable_state_is_not_treated_as_closed(self):
        self.check('''
broken=true;local hidden,why=Visibility.blocked();assert(hidden and why=='menu_state_unavailable')
broken=false;depth=6;assert(Visibility.blocked()==true)
world.view.pointer=function()return nil end;assert(Visibility.blocked()==true)
''')

    def test_runtime_settings_and_visible_cursor_also_hide(self):
        self.check('''
runtime_open=true;local hidden,why=Visibility.blocked();assert(hidden and why=='runtime_settings')
runtime_open=false;stingray.Window.show_cursor=function()return true end
hidden,why=Visibility.blocked();assert(hidden and why=='cursor_visible')
stingray.Window.show_cursor=function()error('missing')end
assert(Visibility.blocked()==false)
''')
