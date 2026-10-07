"""Mod screen overlays (hd2.ui.overlay; runtime/mod_overlay.lua, docs/ui-overlay.md) against a recording fake of the
engine GUI API: retained primitives updated only when they change, top-left coordinates, the layer band, the
temporaries ring handed back after every pass, the Ui World followed, failures closing the GUI, and ownership."""
import unittest

from support import run

HARNESS = r'''
local logged={}
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local events=require('hd2runtime/runtime/events')
events.reset_for_tests()
local calls,ids,temp={},0,0
local function newid()ids=ids+1;return ids end
local function rec(name,ret)return function(...)calls[#calls+1]={name=name,args={...}};if ret then return ret(...)end end end
local function called(name)local n=0;for _,c in ipairs(calls)do if c.name==name then n=n+1 end end;return n end
local function last(name)for i=#calls,1,-1 do if calls[i].name==name then return calls[i]end end end
local W,H=1920,1080
local WORLDS={'GAME','UI'}
local UPDATE_TEXT=true
rawset(_G,'stingray',{
    Application={main_world=function()return 'GAME'end,worlds=function()return WORLDS end},
    World={create_screen_gui=rec('create_screen_gui',function()return 'GUI'..newid()end),destroy_gui=rec('destroy_gui')},
    Gui={resolution=function()return W,H end,rect=rec('rect',newid),update_rect=rec('update_rect'),text=rec('text',newid),
        update_text=rec('update_text'),bitmap=rec('bitmap',newid),destroy_rect=rec('destroy_rect'),
        destroy_text=rec('destroy_text'),destroy_bitmap=rec('destroy_bitmap')},
    Vector2=function(x,y)temp=temp+16;return{x,y}end,Vector3=function(x,y,z)temp=temp+16;return{x,y,z}end,
    Color=function(a,r,g,b)temp=temp+16;return{a,r,g,b}end,
    Script={temp_count=function()return temp end,set_temp_count=function(n)temp=n end}})
local O=require('hd2runtime/runtime/mod_overlay')
O.reset_for_tests()
local UI='UI'
local fonts=require('hd2runtime/domains/ui_fonts').fonts
O.hooks.world=function()if UI==nil then return nil,'no world yet'end;return {runtime={}},UI end
O.hooks.font=function(world,role)return role=='mono'and fonts.monaco or fonts[role]end
O.hooks.mouse=function()return {x=960,y=540,w=1920,h=1080,left=true}end
local hd2=require('hd2runtime/api/hd2')
local function frames(n)for _=1,(n or 1)do if update then update(1/60)end end end
local function args(c)return c.args end
'''


class OverlayTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body), b'ok')

    def test_draws_in_the_ui_world_and_only_changes_what_changed(self):
        self.lua(r'''
local colour={255,0,0}
local label='SCORE 0'
local ov=hd2.ui.overlay({owner='mods/t/arcade'})
assert(ov.layer==1011 and ov.id=='main')
ov:draw(function(d,dt)
    assert(d.width==1920 and d.height==1080 and dt>0)
    d:rect(10,20,100,50,colour)
    d:text(label,10,100,{size=24,colour='#FFFFFF'})
end)
frames(1)
local gui=last('create_screen_gui')
assert(gui.args[1]=='UI'and gui.args[2]=='scale','a retained screen GUI in the Ui World')
assert(called('rect')==1 and called('text')==1)
-- Top-left coordinates: the rectangle's bottom edge is at 1080 - 70 in the engine's bottom-left pixels; layer 1011.
local r=last('rect').args
assert(r[2][1]==10 and r[2][2]==1010 and r[2][3]==1011 and r[3][1]==100 and r[3][2]==50,'rect '..r[2][2])
assert(r[4][1]==255 and r[4][2]==255 and r[4][3]==0,'colour {a, r, g, b}')
local t=last('text').args
local ascent=fonts.body.ascent*24/fonts.body.em
assert(t[2]=='SCORE 0'and t[3]==fonts.body.name and t[5]==fonts.body.name and math.abs(t[6][2]-(1080-100-ascent))<1e-6)
-- An unchanged frame calls nothing; the temporaries ring is handed back after every pass.
local n=#calls;local before=temp
frames(10)
assert(#calls==n,'unchanged frames make no engine call: '..(#calls-n))
assert(temp==before,'temporaries handed back')
-- A colour change updates the rectangle; a text change updates the text (no new primitive).
colour={0,255,0};frames(1)
assert(called('update_rect')==1 and called('rect')==1 and called('update_text')==0)
label='SCORE 10';frames(1)
assert(called('update_text')==1 and called('text')==1 and last('update_text').args[3]=='SCORE 10')
assert(temp==before,'temporaries handed back after the updates')
assert(ov:status().items==2 and ov:status().state=='drawing'and ov:status().frames==13)
return 'ok'
''')

    def test_items_added_removed_and_changing_kind(self):
        self.lua(r'''
local count_items=3
local text_first=false
local ov=hd2.ui.overlay({owner='mods/t/list',id='list',layer=1000})
ov:draw(function(d)
    if text_first then d:text('A',0,0)end
    for i=1,count_items do d:rect(0,i*10,5,5,{1,2,3},i)end
end)
frames(1)
assert(called('rect')==3 and last('rect').args[2][3]==1003,'z offsets inside the band')
count_items=1;frames(1)
assert(called('destroy_rect')==2,'two removed')
count_items=2;frames(1)
assert(called('rect')==4)
-- The first item changes kind: destroyed and created again.
text_first=true;frames(1)
assert(called('destroy_rect')>=3 and called('text')==1)
return 'ok'
''')

    def test_invalid_items_are_refused_and_never_reach_the_engine(self):
        self.lua(r'''
local ov=hd2.ui.overlay({owner='mods/t/bad'})
ov:draw(function(d)
    d:rect(0/0,0,10,10)                    -- not finite
    d:rect(0,0,10,10,{1,2,3},13)           -- 1011 + 13 > 1023
    d:rect(0,0,10,10,'#12345')             -- bad colour
    d:text('line\nbreak',0,0)              -- control character
    d:text(string.rep('x',161),0,0)        -- too long
    d:text('ok',0,0,{font='comic'})        -- unknown font role
    d:rect(5000,5000,10,10)                -- fully off screen: dropped quietly
    d:rect(-50,-50,100,100,{9,9,9})        -- clipped to the screen
end)
frames(1)
assert(called('rect')==1 and called('text')==0)
local r=last('rect').args
assert(r[2][1]==0 and r[3][1]==50 and r[3][2]==50 and r[2][2]==1030,'clipped')
local s=ov:status()
assert(s.refused==6 and s.first_refusal=='invalid rectangle',s.refused..' '..tostring(s.first_refusal))
assert(not pcall(hd2.ui.overlay,{owner='mods/t/bad',id='x',layer=2000}))
assert(not pcall(hd2.ui.overlay,{owner='mods/t/bad',id='bad id!'}))
return 'ok'
''')

    def test_follows_the_ui_world_and_hides_shows_and_closes(self):
        self.lua(r'''
local ov=hd2.ui.overlay({owner='mods/t/w'})
ov:draw(function(d)d:rect(0,0,10,10)end)
frames(1);assert(called('create_screen_gui')==1)
-- A new Ui World (ship <-> mission): the GUI is opened again there.
WORLDS={'GAME','UI2'};UI='UI2';frames(1)
assert(called('create_screen_gui')==2 and last('create_screen_gui').args[1]=='UI2')
-- No world: closed and waiting.
UI=nil;frames(1)
assert(ov:status().state=='waiting'and ov:status().reason=='no world yet')
UI='UI2';frames(1);assert(called('create_screen_gui')==3)
ov:hide();frames(1)
assert(called('destroy_gui')==2 and ov:status().state=='hidden')
ov:show();frames(1);assert(called('create_screen_gui')==4)
ov:close();frames(3)
assert(ov:status().state=='closed'and called('create_screen_gui')==4 and called('destroy_gui')==3)
assert(#hd2.ui.overlays()==0)
return 'ok'
''')

    def test_a_failing_draw_function_hides_the_overlay_and_is_attributed_to_the_mod(self):
        self.lua(r'''
local broken=true
local ov=hd2.ui.overlay({owner='mods/t/err'})
ov:draw(function(d)d:rect(0,0,10,10);if broken then error('oops')end end)
frames(1)
assert(called('rect')==0 and ov:status().state=='error')
assert(count('frame callback failed (mod mods/t/err')==1 and count('oops')>=1)
broken=false;frames(1)
assert(called('rect')==1 and ov:status().state=='drawing')
-- An engine failure closes the GUI (logged once) and it is opened again later.
stingray.Gui.update_rect=function()error('engine says no')end
ov:draw(function(d)d:rect(0,0,20,10)end);frames(1)
assert(ov:status().state=='failed'and count('engine GUI call failed')==1)
stingray.Gui.update_rect=rec('update_rect')
frames(1);assert(ov:status().state=='drawing')
return 'ok'
''')

    def test_without_update_text_a_changed_text_is_replaced(self):
        self.lua(r'''
stingray.Gui.update_text=nil
local text='A'
local ov=hd2.ui.overlay({owner='mods/t/txt'})
ov:draw(function(d)d:text(text,100,100,{align='center'})end)
frames(1);text='B';frames(1)
assert(called('destroy_text')==1 and called('text')==2)
return 'ok'
''')

    def test_owner_from_the_mod_scope_mouse_and_text_width(self):
        self.lua(r'''
local ov
hd2.events.run_as('mods/t/scoped',function()ov=hd2.ui.overlay()end)
assert(ov.owner=='mods/t/scoped')
assert(hd2.ui.overlay({owner='mods/t/scoped'})==ov,'the same object')
ov:draw(function(d)d:rect(0,0,1,1)end);frames(1)
local m=ov:mouse();assert(m.x==960 and m.y==540 and m.left)
assert(ov:text_width('WW',20)>ov:text_width('ii',20))
assert(not pcall(hd2.ui.overlay),'no mod scope: refused')
local c=hd2.ui.colour('#10203040');assert(c[1]==16 and c[4]==64)
return 'ok'
''')

    def test_engine_gui_reads_the_bindings_argument_order(self):
        self.lua(r'''
local engine_gui=require('hd2runtime/runtime/engine_gui')
local screen=assert(engine_gui.open({world='UI',max_layer=1023}))
local id=screen.text('x','f',10,'f',1,2,3,{255,1,2,3})
assert(screen.update_text(id,'y','f',11,'f',4,5,6,{255,1,2,3}))
local u=last('update_text').args
assert(u[1]:match('^GUI')and u[2]==id and u[3]=='y'and u[4]=='f'and u[5]==11 and u[6]=='f'and u[7][1]==4 and u[8][2]==1)
assert(screen.destroy('text',id))
local d=last('destroy_text').args;assert(d[2]==id and#d==2)
assert(not screen.destroy('rect','x')and not screen.destroy('circle',1))
-- temp_scope: one integer in, one integer out (this build's Script.temp_count).
temp=100
local ok,v=engine_gui.temp_scope(function()stingray.Vector3(1,2,3);return 7 end)
assert(ok and v==7 and temp==100)
local bad=engine_gui.temp_scope(function()stingray.Vector3(1,2,3);error('x')end)
assert(bad==false and temp==100)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
