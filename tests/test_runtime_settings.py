"""The HD2Runtime settings panel (0.30.2, runtime/runtime_settings.lua; docs/getting-started.md "Settings (F10)"):
  * F10 is bound by the Runtime itself and opens a window in the HD2R Editor's look, centred, scaled with the screen;
  * every setting is on by default; a click on a row turns it off or on (saved through the store; in memory offline);
  * Esc or the x closes it; a held button when it opens is not a click;
  * each setting turns its own on-screen item off at once: the startup notice, the alert cards, the version label and
    the startup progress panel (the log keeps every line)."""
import unittest

from support import run

HARNESS = r'''
local settings=require('hd2runtime/runtime/runtime_settings')
settings.reset_for_tests()
local saved={}
settings.hooks.store=function()return {get=function(_,k)return saved[k]end,set=function(_,k,v)saved[k]=v end}end
-- A frame builder recording what one frame draws (top-left origin, like the mod overlay's).
local function builder(w,h)
    local d={width=w,height=h,scale=math.min(w/1920,h/1080),rects={},texts={}}
    function d:rect(x,y,rw,rh,c,z)self.rects[#self.rects+1]={x=x,y=y,w=rw,h=rh,c=c,z=z}end
    function d:text(s,x,y,o)self.texts[#self.texts+1]={s=s,x=x,y=y,size=o.size,colour=o.colour,font=o.font}end
    function d:text_width(s,size)return#s*size*0.55 end
    function d:wrap(s)return {s}end
    return d
end
local keys={}
local input={pressed=function(name)return keys[name]==true end}
local function has(d,s)for _,t in ipairs(d.texts)do if t.s==s then return true end end;return false end
'''


def lua(body):
    return run(HARNESS + body + "\nreturn 'ok'")


class RuntimeSettingsTests(unittest.TestCase):
    def test_input_blocking_and_sounds_follow_visible_panel_lifetime(self):
        self.check(r'''
local events=require('hd2runtime/runtime/events')
local blocking,sounds={},{}
settings.hooks.block=function(on)blocking[#blocking+1]=on end
settings.hooks.sound=function(event)sounds[#sounds+1]=event;return true end
settings.open('performance')
assert(settings.visible()and blocking[#blocking]and sounds[1]=='ui/slot_select')
events.state.now=1
settings.select_tab('settings');assert(sounds[#sounds]=='ui/generic_select')
events.state.now=2;keys.ESCAPE=true
settings.draw(builder(1920,1080),nil,input)
assert(not settings.visible()and blocking[#blocking]==false)
assert(sounds[#sounds]=='ui/picker_close')
local n=#sounds;events.tick(1);assert(#sounds==n,'no background sounds')
settings.set('ui_sounds',false);settings.open();settings.close();assert(#sounds==n,'mute')
settings.set('ui_sounds',true);events.state.now=4
local attempts=0;settings.hooks.sound=function()attempts=attempts+1;return nil end
settings.sound('click');events.state.now=5;settings.sound('click');assert(attempts==1)
events.state.now=35;settings.sound('click');assert(attempts==2,'bounded retry')
''')

    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_global_filter_badges_paging_and_return_to_runtime_details(self):
        self.check(r'''
local perf=require('hd2runtime/runtime/perf_watch')
local monitor=require('hd2runtime/runtime/performance_panel')
require('hd2runtime/runtime/metrics').set_clock(function()return 0 end)
CowboyBingusModLoader={modules={}}
for i=1,15 do CowboyBingusModLoader.modules[('mods/test/asset_%02d'):format(i)]='loaded'end
settings.select_tab('performance')
local L=settings.layout(1920,1080,1)
local function click(id)
    local box;for _,v in ipairs(monitor.controls(L.content,L.k))do if v.id==id then box=v end end
    local m={x=box.x+box.w/2,y=box.y+box.h/2,left=false}
    settings.draw(builder(1920,1080),m,input);m.left=true
    settings.draw(builder(1920,1080),m,input)
end
click('global');assert(monitor.mode()=='global')
local t=perf.begin();perf.finish(t,'mods/skyeshade/hd2runtime_editor','editor');perf.update(0.25)
local d=builder(1920,1080);settings.draw(d,nil,input)
assert(has(d,'HD2R Editor')and has(d,'[R]')and has(d,'Not measured')and has(d,'Page 1 / 4'))
click('next');d=builder(1920,1080);settings.draw(d,nil,input)
assert(has(d,'Page 2 / 4')and has(d,'asset 05')and not has(d,'HD2R Editor'))
click('runtime');assert(monitor.mode()=='runtime'and perf.history().head==1)
t=perf.begin();perf.finish(t,'HD2Runtime',{perf_name='event: mission_started / example'});perf.update(0.25)
d=builder(1920,1080);settings.draw(d,nil,input)
assert(has(d,'event: mission_started / example')and not has(d,'asset 07'))
settings.close();assert(not perf.recording())
''')

    def test_every_setting_is_on_by_default_and_a_click_turns_it_off_and_saves_it(self):
        self.check(r'''
for _,item in ipairs(settings.ITEMS)do
    assert(settings.enabled(item.key)==(item.key~='optimized_application'),item.key)
end
local heard={}
settings.on_change(function(k,on)heard[#heard+1]=k..'='..tostring(on)end)
local d=builder(1920,1080)
local L=settings.draw(d,nil,input)
assert(has(d,'HD2R')and has(d,'RUNTIME')and has(d,'MESSAGES ON SCREEN')and has(d,'Version label'))
-- Click the version label row: press (left down after up) inside its box.
local row
for _,r in ipairs(L.rows)do if r.item.key=='version_label'then row=r end end
local m={x=row.box.x+row.box.w/2,y=row.box.y+row.box.h/2,left=false}
settings.draw(builder(1920,1080),m,input)
m.left=true
settings.draw(builder(1920,1080),m,input)
assert(settings.enabled('version_label')==false and saved['show.version_label']==false)
assert(heard[1]=='version_label=false')
-- Holding the button is one click, not a toggle every frame.
settings.draw(builder(1920,1080),m,input)
assert(settings.enabled('version_label')==false)
m.left=false;settings.draw(builder(1920,1080),m,input)
m.left=true;settings.draw(builder(1920,1080),m,input)
assert(settings.enabled('version_label')==true,'a second click turns it back on')
''')

    def test_faster_application_is_off_by_default_and_the_saved_choice_sets_the_mode(self):
        # 0.40.1: the 0.40.0 application optimizations are off unless turned on (runtime/application_mode.lua).
        self.check(r'''
local mode=require('hd2runtime/runtime/application_mode')
mode.configure(false)
assert(settings.enabled('optimized_application')==false and saved['show.optimized_application']==nil)
settings.start()
assert(mode.enabled()==false,'off unless saved on')
local d=builder(1920,1080)
local L=settings.draw(d,nil,input)
assert(has(d,'Faster application (0.40.0)'))
local row
for _,r in ipairs(L.rows)do if r.item.key=='optimized_application'then row=r end end
local m={x=row.box.x+row.box.w/2,y=row.box.y+row.box.h/2,left=false}
settings.draw(builder(1920,1080),m,input)
m.left=true;settings.draw(builder(1920,1080),m,input)
assert(saved['show.optimized_application']==true and mode.enabled()==true,'a click turns it on, saved')
settings.set('optimized_application',false)
assert(saved['show.optimized_application']==false and mode.enabled()==false)
-- The editor's switch: the diagnostics API saves the same setting.
local hd2=require('hd2runtime/api/hd2')
assert(hd2.diagnostics.save_application_optimizations(true)==true)
assert(saved['show.optimized_application']==true and mode.enabled()==true)
-- The process-only call does not save.
hd2.diagnostics.application_optimizations(false)
assert(mode.enabled()==false and saved['show.optimized_application']==true)
''')

    def test_the_window_is_centred_and_fits_at_every_resolution(self):
        self.check(r'''
for _,res in ipairs({{1920,1080},{2560,1440},{3840,2160},{1280,720},{3440,1440},{1024,768}})do
    local L=settings.layout(res[1],res[2],math.min(res[1]/1920,res[2]/1080))
    assert(L.x>=0 and L.y>=0 and L.x+L.w<=res[1]and L.y+L.h<=res[2],'fits at '..res[1]..'x'..res[2])
    assert(math.abs((L.x+L.w/2)-res[1]/2)<=1 and math.abs((L.y+L.h/2)-res[2]/2)<=1,'centred')
    assert(#L.rows==#settings.ITEMS)
end
-- The same share of the height at 1080p and 4K.
local a,b=settings.layout(1920,1080,1),settings.layout(3840,2160,2)
assert(math.abs(a.h/1080-b.h/2160)<1e-9)
''')

    def test_esc_and_the_close_box_close_it(self):
        self.check(r'''
local closed=0
settings.close=function()closed=closed+1 end
keys.ESCAPE=true
settings.draw(builder(1920,1080),nil,input)
keys.ESCAPE=false
assert(closed==1)
local L=settings.layout(1920,1080,1)
local m={x=L.close.x+5,y=L.close.y+5,left=false}
settings.draw(builder(1920,1080),m,input)
m.left=true
settings.draw(builder(1920,1080),m,input)
assert(closed==2)
''')

    def test_f10_is_the_runtime_s_own_binding(self):
        self.check(r'''
local b=settings.start()
assert(b and b.id=='hd2runtime.settings'and b.key=='F10'and b.owner=='hd2runtime',tostring(b and b.key))
assert(settings.start()==b,'bound once')
''')

    def test_each_setting_hides_its_own_item(self):
        self.check(r'''
-- The alert cards: refused while off; a card on screen goes at once.
local card=require('hd2runtime/runtime/stratagem_alert')
card.reset_for_tests()
settings.set('alert_cards',false)
assert(card.post({key='x',severity='warn',title='Custom stratagems',items={{line='a'}}})==false)
settings.set('alert_cards',true)
assert(card.post({key='x',severity='warn',title='Custom stratagems',items={{line='a'}}})==true)
settings.set('alert_cards',false)
card.tick_for_tests(0.1)
assert(card.status().queued==0,'cleared when turned off')
-- The version label: hidden while off.
local label=require('hd2runtime/runtime/version_label')
label.reset_for_tests()
local opened=0
label.hooks.state=function()return {name='Ship'}end
label.hooks.world=function()return {}end
label.hooks.font=function()return 'f'end
label.hooks.open_screen=function()opened=opened+1
    return {width=1920,height=1080,text=function()return 1 end,close=function()end}end
settings.set('version_label',false)
label.start()
for _=1,8 do update(0.1)end
assert(opened==0 and label.status()==nil,'no label while off')
settings.set('version_label',true)
for _=1,8 do update(0.1)end
assert(opened==1 and label.status(),'shown again when turned on')
label.reset_for_tests()
''')


    def test_interface_size_steps_saves_and_keeps_to_the_screen(self):
        self.check(r'''
assert(settings.value('ui_scale')==1)
local a=settings.layout(1920,1080,1)
-- + twice: 110 %, then 125 %, saved; the window grows with it
local function click(box)
    local m={x=box.x+box.w/2,y=box.y+box.h/2,left=false}
    settings.draw(builder(1920,1080),m,input)
    m.left=true;settings.draw(builder(1920,1080),m,input)
end
click(settings.layout(1920,1080,1).size_up)
click(settings.layout(1920,1080,1).size_up)
assert(settings.value('ui_scale')==1.25 and saved['setting.ui_scale']==1.25,tostring(settings.value('ui_scale')))
local b=settings.layout(1920,1080,1)
assert(math.abs(b.w/a.w-1.25)<1e-9 and b.k==1.25)
local d=builder(1920,1080);settings.draw(d,nil,input)
assert(has(d,'INTERFACE')and has(d,'Interface size')and has(d,'125%'))
-- the largest size fits every real screen (the overlay's scale follows the smaller ratio)
for _=1,5 do settings.step_ui_scale(1)end
assert(settings.value('ui_scale')==1.5)
for _,res in ipairs({{1920,1080},{1280,720},{1024,768},{3440,1440},{1920,1200}})do
    local L=settings.layout(res[1],res[2],math.min(res[1]/1920,res[2]/1080))
    assert(L.x>=0 and L.y>=0 and L.x+L.w<=res[1]and L.y+L.h<=res[2]and math.abs(L.fits-1.5)<1e-9,res[1]..'x'..res[2])
end
-- an overlay shorter than its scale says: kept to what fits, and the panel says so
local L=settings.layout(1920,900,1)
assert(L.y>=0 and L.y+L.h<=900 and L.fits<1.5)
d=builder(1920,900);d.scale=1;settings.draw(d,nil,input)
assert(has(d,('(%d%% fits this screen)'):format(math.floor(L.fits*100+0.5))),'the size that fits is shown')
-- - steps down to 90 % and no further; an unknown saved size is the default
for _=1,8 do settings.step_ui_scale(-1)end
assert(settings.value('ui_scale')==0.9)
saved['setting.ui_scale']=3
assert(settings.value('ui_scale')==1)
''')

    def test_the_performance_tab_measures_only_while_shown_and_graphs_every_part(self):
        self.check(r'''
local perf=require('hd2runtime/runtime/perf_watch')
local metrics=require('hd2runtime/runtime/metrics')
perf.reset_for_tests()
local T=0
metrics.set_clock(function()return T end)
local function work(owner,key,seconds,label)
    local timed=perf.begin();T=T+seconds
    perf.finish(timed,owner,key,function()return label or tostring(key)end)
end
-- The settings tab measures nothing.
settings.draw(builder(1920,1080),nil,input)
assert(not perf.recording())
-- A click on PERFORMANCE switches tabs; drawing it starts the measurements.
local L=settings.layout(1920,1080,1)
local tab=L.tabs[2]
assert(tab.tab.id=='performance')
local m={x=tab.box.x+tab.box.w/2,y=tab.box.y+tab.box.h/2,left=false}
settings.draw(builder(1920,1080),m,input)
m.left=true;settings.draw(builder(1920,1080),m,input)
assert(settings.tab()=='performance')
m.left=false
local d=builder(1920,1080);settings.draw(d,m,input)
assert(perf.recording()and has(d,'PERFORMANCE')and has(d,'Measuring...'))
-- Two mods and a part of the Runtime, for 3 seconds of 60 updates a second.
local watch={}
for _=1,180 do
    work('mods/x/hog','a',0.004)
    work('mods/y/small','b',0.0005)
    work('HD2Runtime',watch,0.001,'update of hd2runtime/runtime/custom_stratagems')
    perf.update(1/60)
end
d=builder(1920,1080);settings.draw(d,m,input)
assert(has(d,'Runtime and mods: 5.50 ms per frame'),'the total per update')
assert(has(d,'33.0% of the frame time  |  60 FPS'))
assert(has(d,'hog')and has(d,'small')and has(d,'custom stratagems')and has(d,'HD2R')and has(d,'[R]'))
assert(has(d,'4.00 ms')and has(d,'0.50 ms'))
-- Page navigation sits beside the footer number, with an opaque dark background.
local controls=require('hd2runtime/runtime/performance_panel').controls(L.content,L.k)
local page
for _,t in ipairs(d.texts)do if t.s=='Page 1 / 1'then page=t end end
assert(page,'page number missing')
for _,id in ipairs({'previous','next'})do
 local c
 for _,control in ipairs(controls)do if control.id==id then c=control end end
 assert(c,'navigation control absent')
 assert(math.abs(c.y+c.h/2-(page.y+page.size*settings.CAP_OFFSET))<0.001 and c.x>page.x,'navigation is not beside page number')
 local background
 for _,r in ipairs(d.rects)do
  if r.x==c.x and r.y==c.y and r.w==c.w and r.h==c.h then background=r.c end
 end
 assert(background and background[4]==255 and background[1]<40,'navigation background must be dark and opaque')
end
-- the heaviest first in the table
local order={}
for _,t in ipairs(d.texts)do if t.s=='hog'or t.s=='small'or t.s=='custom stratagems'then order[#order+1]=t.s end end
assert(order[1]=='hog'and order[2]=='custom stratagems'and order[3]=='small',table.concat(order,','))
-- 0.31.2: what the tab draws is built once per bin; another frame in the same bin replays it exactly (only the window's
-- footer is fitted again, no row name).
local fits=0
local again=builder(1920,1080)
local wrap=again.wrap
function again:wrap(s,...)fits=fits+1;return wrap(self,s,...)end
settings.draw(again,m,input)
assert(fits==1,'fitted again: '..fits)
assert(#again.rects==#d.rects and #again.texts==#d.texts)
for i,t in ipairs(d.texts)do
    local u=again.texts[i]
    assert(u.s==t.s and u.x==t.x and u.y==t.y and u.size==t.size and u.colour==t.colour,'text '..i)
end
for i,r in ipairs(d.rects)do
    local u=again.rects[i]
    assert(u.x==r.x and u.y==r.y and u.w==r.w and u.h==r.h and u.c==r.c and u.z==r.z,'rect '..i)
end
-- Every column draws six rectangles: the frame's rectangle count does not change when a bin completes.
local count=#d.rects
for _=1,15 do work('mods/x/hog','a',0.004);perf.update(1/60)end
local e=builder(1920,1080);settings.draw(e,m,input)
assert(#e.rects==count,#e.rects..' vs '..count)
-- Back to SETTINGS, or closing: the measurements stop and are dropped.
settings.select_tab('settings')
assert(not perf.recording()and perf.history()==nil)
settings.select_tab('performance');settings.draw(builder(1920,1080),m,input)
assert(perf.recording())
settings.close()
assert(not perf.recording())
''')


if __name__ == '__main__':
    unittest.main()
