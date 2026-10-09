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
    return d
end
local keys={}
local input={pressed=function(name)return keys[name]==true end}
local function has(d,s)for _,t in ipairs(d.texts)do if t.s==s then return true end end;return false end
'''


def lua(body):
    return run(HARNESS + body + "\nreturn 'ok'")


class RuntimeSettingsTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_every_setting_is_on_by_default_and_a_click_turns_it_off_and_saves_it(self):
        self.check(r'''
for _,item in ipairs(settings.ITEMS)do assert(settings.enabled(item.key),item.key)end
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


if __name__ == '__main__':
    unittest.main()
