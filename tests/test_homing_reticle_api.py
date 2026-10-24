import unittest
from homing_test_support import run

class ReticleApiTests(unittest.TestCase):
    def test_real_event_scheduler_accepts_each_reticle_and_runs_its_lifecycle(self):
        self.assertEqual(run('''
package.preload['hd2runtime/runtime/metrics']=function()return{
 count=function()end,start=function()return 0 end,elapsed=function()end}end
package.preload['hd2runtime/runtime/perf_watch']=function()return{
 register_mod=function()end,begin=function()return 0 end,finish=function()end}end
package.preload['hd2runtime/runtime/scheduler']=function()return{attach=function()end}end
package.preload['hd2runtime/runtime/log']=function()return{emit=function()end}end
package.preload['hd2runtime/domains/events_catalog']=function()return{names={},events={}}end
package.preload['hd2runtime/runtime/homing_view']=function()return{}end
package.preload['hd2runtime/runtime/homing_visibility']=function()return{blocked=function()return false end}end
local renderers={}
package.preload['hd2runtime/runtime/homing_reticle']=function()return{
 validate_style=function()end,new=function()
  local r={ticks=0,stopped=false}
  function r:update()end
  function r:tick()self.ticks=self.ticks+1 end
  function r:shutdown()self.stopped=true end
  function r:status()return{}end
  renderers[#renderers+1]=r;return r
 end}end
local events=require('hd2runtime/runtime/events')
local api=require('hd2runtime/api/homing_reticle')
local function handle(weapon)return{status='active',owner='mods/test',weapon=weapon,
 _lock={visual_snapshot=function()return{visible=false}end}}end
local first=handle('AR-23 Liberator');local a=api.open(first,{})
local second=handle('R-63CS Diligence Counter Sniper');local b=api.open(second,{})
assert(#events.state.frames==2,'each reticle must register an accepted frame callback')
events.tick(.016)
assert(renderers[1].ticks==1 and renderers[2].ticks==1,'both reticles need every-frame clearing')
a:stop();events.tick(.016)
assert(renderers[1].ticks==1 and renderers[2].ticks==2,'stopping one reticle must preserve another')
second.status='stopped';events.tick(.016)
assert(renderers[2].stopped and #events.state.frames==0,'stopping gameplay must remove the callback')
b:stop()
''',('runtime/events','api/homing_reticle')),b'ok')

    def test_style_hide_replacement_and_stop_are_visual_only(self):
        self.assertEqual(run('''
local cancelled=0;local callback
package.preload['hd2runtime/runtime/events']=function()return{
 emit_log=function()end,frame=function(fn)callback=fn;return{cancel=function()cancelled=cancelled+1 end}end}end
package.preload['hd2runtime/runtime/homing_view']=function()return{project=function()end,radius=function()end}end
package.preload['hd2runtime/runtime/homing_visibility']=function()return{blocked=function()return true end}end
local handle={status='active',owner='mod/a',weapon='AR-23 Liberator',_lock={
 visual_snapshot=function()return{visible=false}end}}
local api=require('hd2runtime/api/homing_reticle')
local r=api.open(handle,{locked_color='#FFFFFF'});assert(r:status().visible)
local observer=handle._lock.on_visual
r:hide();assert(not r:status().visible and handle.status=='active')
r:style({marker_shape='cross',ring=false});r:show()
assert(handle._lock.on_visual==observer and handle.status=='active')
assert(not pcall(r.style,r,{ring_segments=1}));assert(r:status().visible)
callback();r:stop();r:stop();assert(cancelled==1 and handle._lock.on_visual==nil)
assert(handle.status=='active','HUD stop must not stop homing')
handle.status='refused';assert(not pcall(api.open,handle,{}))
''',('runtime/homing_reticle_style','runtime/homing_reticle','api/homing_reticle')),b'ok')
