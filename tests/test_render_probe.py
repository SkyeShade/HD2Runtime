"""The render-order probe (development; docs/custom-stratagems.md, "Render order"; runtime/render_probe.lua): over native
stratagem cards and in an empty screen area it draws a TEST RECTANGLE, one rectangle per layer, retained GUIs created in
a known order and an immediate GUI, and on request a script world rendered through the 'overlay' viewport from the
engine's Lua render callback. Offline: the event world with a loadout screen and a scrolled native grid, and a recording
stand-in for the engine GUI and world API with the engine's own types and returns (nothing is drawn). Nothing is
written."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

PROBE = r"""
local probe=require('hd2runtime/runtime/render_probe')
local engine_gui=require('hd2runtime/runtime/engine_gui')
local RENDER=SEL.render
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT},units={RENDER.cameraUnit},
    shading={RENDER.shading}})
-- The script-world bindings as the engine's: new_world returns the world and lists it, create_viewport, the shading
-- environment, spawn_unit and Unit.camera return one value; render_world, destroy_viewport, destroy_shading_environment
-- and release_world return nothing (exe 0x3F7C10, 0x3F9AA0, 0x3F7E90, 0x3F8130).
local NEW=newproxy(true)
engine.Application.new_world=function(...)calls[#calls+1]={name='new_world',args={...}};alive[#alive+1]=NEW;return NEW end
engine.Application.create_viewport=rec('create_viewport')
engine.Application.destroy_viewport=nothing('destroy_viewport')
engine.Application.render_world=nothing('render_world')
engine.Application.release_world=function(w)
    calls[#calls+1]={name='release_world',args={w}}
    for i=#alive,1,-1 do if alive[i]==w then table.remove(alive,i)end end
end
engine.World.create_shading_environment=rec('create_shading_environment')
engine.World.destroy_shading_environment=nothing('destroy_shading_environment')
engine.World.spawn_unit=rec('spawn_unit')
engine.Unit={camera=rec('camera')}
-- (Gui.rect(gui, position, ...), Gui.text(gui, s, font, size, material, position, ...).)
local function at(c)return c.name=='rect'and c.args[2]or c.name=='text'and c.args[6]or c.name=='bitmap'and c.args[3]end
local function rects_in(gui)local out={};for _,c in ipairs(calls)do if c.name=='rect'and c.args[1]==gui then out[#out+1]=c end end;return out end
local function screens()local out={};for k,c in ipairs(calls)do if c.name=='create_screen_gui'then out[#out+1]={id=k,args=c.args}end end;return out end
local ROWS,SECTIONS={4,4,4,4,4,4,4,4,4,2},{0,4,7}
local ORIGINAL_RENDER=function(...)return 'original',...end
rawset(_G,'render',ORIGINAL_RENDER)
"""


def lua(body):
    return run(WORLD + SELECT + PROBE + body)


class RenderProbeTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_engine_gui_options_are_validated(self):
        self.check(r'''
-- The default range stops at 999; the probe's wider range reaches 10000 and no further.
local s=assert(engine_gui.open())
assert(s.rect(10,10,999,5,5,{255,1,2,3})and s.rect(10,10,1000,5,5,{255,1,2,3})==nil)
s.close()
local wide=assert(engine_gui.open({max_layer=10000}))
assert(wide.rect(10,10,10000,5,5,{255,1,2,3})and wide.rect(10,10,10001,5,5,{255,1,2,3})==nil)
wide.close()
assert(select(2,engine_gui.open({max_layer=10001}))=='invalid layer range')
assert(select(2,engine_gui.open({max_layer=1.5}))=='invalid layer range')
assert(select(2,engine_gui.open({mode='layered'}))=='unknown GUI mode')
-- Immediate mode is created as the engine's performance HUD script creates it.
local before=#calls
local imm=assert(engine_gui.open({mode='immediate'}))
assert(calls[before+1].name=='create_screen_gui'and calls[before+1].args[1]==MAIN and calls[before+1].args[2]==0
    and calls[before+1].args[3]==0 and calls[before+1].args[4]=='immediate')
imm.close()
-- A chosen world must be listed.
assert(select(2,engine_gui.open({world=newproxy(true)}))=='the world is not among the worlds')
local main,index,count=engine_gui.main_world()
assert(main==MAIN and index==1 and count==1 and engine_gui.index_of(MAIN)==1)
-- The script world: only known templates; built as the performance HUD builds one; released in reverse.
assert(select(2,engine_gui.script_world('hud_world_ui_and_composite_layer'))=='unknown viewport template')
before=#calls
local w=assert(engine_gui.script_world('overlay'))
local names={}
for k=before+1,#calls do names[#names+1]=calls[k].name end
assert(table.concat(names,',')=='new_world,create_viewport,create_shading_environment,spawn_unit,camera',
    table.concat(names,','))
assert(calls[before+2].args[1]==NEW and calls[before+2].args[2]=='overlay'
    and calls[before+3].args[2]==RENDER.shading and calls[before+4].args[2]==RENDER.cameraUnit
    and calls[before+5].args[2]=='camera')
assert(w.render())
local r=calls[#calls]
-- render_world(world, camera, viewport, shading): the ids the stand-in returned for them (their call numbers).
assert(r.name=='render_world'and r.args[1]==NEW and r.args[2]==before+5 and r.args[3]==before+2 and r.args[4]==before+3)
w.release()
assert(calls[#calls].name=='release_world'and calls[#calls-1].name=='destroy_shading_environment'
    and calls[#calls-2].name=='destroy_viewport'and #alive==1)
assert(select(2,w.render())=='the world is released')
-- A failure part-way releases what was made.
engine.Application.create_viewport=function(...)calls[#calls+1]={name='create_viewport',args={...}}end
local none,why=engine_gui.script_world('overlay')
assert(none==nil and why=='create_viewport returned nothing'and calls[#calls].name=='release_world'and #alive==1)
assert(#W.runtime.writes==0)
return 'ok'
''')

    def test_the_probe_draws_every_experiment_over_native_cards_and_outside(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=1})
local g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=216})
local C=probe.controller()
tick(4)
local world=require('hd2runtime/runtime/event_world').open()
local cards=assert(probe.cards(world,selector.screen(world)))
assert(#cards==4 and cards[1].row==cards[4].row and cards[1].column==0 and cards[4].column==3)
-- Eight screen GUIs in the main world, in this order; the immediate one as the performance HUD makes it.
local s=screens()
assert(#s==8,#s)
for k=1,7 do assert(s[k].args[1]==MAIN and s[k].args[2]=='scale')end
assert(s[8].args[1]==MAIN and s[8].args[4]=='immediate')
assert(count('GUIs created in order: labels, test, layers, A, B, C, D, immediate')==1,table.concat(logged,' | '))
local labels,test,layers,A,B,Cg,Dg,imm=s[1].id,s[2].id,s[3].id,s[4].id,s[5].id,s[6].id,s[7].id,s[8].id
-- TEST RECTANGLE over N0: the edge at 998 and the red body at 999 over exactly that card, and its text.
local n0=cards[1].rect
local t=rects_in(test)
local edge,body
for _,c in ipairs(t)do
    if near(at(c)[1],n0.x)and near(at(c)[2],n0.y)and at(c)[3]==998 then edge=c end
    if at(c)[3]==999 and at(c)[1]>n0.x and at(c)[1]<n0.x+10 then body=c end
end
assert(edge and body and near(edge.args[3][1],n0.w)and near(edge.args[3][2],n0.h),'the test rectangle covers N0')
assert(body.args[4][2]==230 and body.args[4][3]==20,'red')
assert(find('text',2,'TEST')and find('text',2,'RECTANGLE'))
-- LAYERS over N1: one strip per layer, bottom to top, across the card, and one square each outside.
local n1=cards[2].rect
local strips={}
for _,c in ipairs(rects_in(layers))do if near(at(c)[1],n1.x)then strips[#strips+1]=c end end
assert(#strips==5)
for k,layer in ipairs({0,21,100,900,990})do
    assert(at(strips[k])[3]==layer and near(at(strips[k])[2],n1.y+(k-1)*n1.h/5)and near(strips[k].args[3][1],n1.w))
end
assert(#rects_in(layers)==10,'the same five squares outside')
-- GUI ORDER over N2: A before B before C before D, each one rectangle over the card and one outside, all at 500.
assert(labels<test and test<layers and layers<A and A<B and B<Cg and Cg<Dg and Dg<imm)
for _,gui in ipairs({A,B,Cg,Dg})do
    local r=rects_in(gui)
    assert(#r==2 and at(r[1])[3]==500 and at(r[2])[3]==500)
end
local n2=cards[3].rect
local a_card=rects_in(A)[2]
assert(at(a_card)[1]>=n2.x and at(a_card)[1]+a_card.args[3][1]<=n2.x+n2.w+1e-6 and at(a_card)[2]>=n2.y+n2.h*0.5-1e-6)
assert(rects_in(A)[1].args[4][2]==255 and rects_in(A)[1].args[4][3]==0,'A magenta')
assert(rects_in(B)[1].args[4][2]==0,'B cyan')
-- IMMEDIATE: drawn again every frame over N3 and outside, at 999.
local before=#rects_in(imm)
tick(3)
assert(#rects_in(imm)==before+6,'two rectangles a frame')
local n3=cards[4].rect
assert(near(at(rects_in(imm)[#rects_in(imm)])[1],n3.x))
-- Everything inside the screen, and the logs name every placement.
for _,c in ipairs(calls)do
    local p=at(c)
    if p then assert(p[1]>=-1 and p[2]>=-1 and p[1]<=1921 and p[2]<=1081)end
end
for _,text in ipairs({'render probe drawn for slot 1','N0 TEST RECTANGLE over row','N1 LAYERS over row',
        'strips bottom to top 0, 21, 100, 900, 990','N2 GUI ORDER over row','N3 IMMEDIATE over row',
        'O (outside the native UI','render callback function','main_world: worlds()[1]'})do
    assert(count(text)==1,text..' | '..table.concat(logged,' | '))
end
-- Still: nothing redrawn but the immediate rectangles.
local retained=#calls
tick(2)
for k=retained+1,#calls do assert(calls[k].name=='rect'and calls[k].args[1]==imm)end
-- Scrolling: everything closes at once, then is drawn again at the new place.
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=100})
tick(1)
assert(called('destroy_gui')==8)
tick(3)
assert(called('create_screen_gui')==16 and count('render probe drawn for slot 1')==2)
-- F8: layers 2000 and 10000 too, in a GUI that accepts them.
assert(C.toggle_extended():find('added',1,true))
assert(called('destroy_gui')==16)
tick(3)
s=screens()
local wide=s[#s-5].id
local found={}
for _,c in ipairs(rects_in(wide))do found[at(c)[3]]=(found[at(c)[3]]or 0)+1 end
assert(found[2000]==2 and found[10000]==2 and count('strips bottom to top 0, 21, 100, 900, 990, 2000, 10000')==1)
-- Closing the grid removes it all.
SCREEN.close()
tick(2)
assert(called('destroy_gui')==called('create_screen_gui')and count('render probe removed (the')==1,table.concat(logged,' | '))
C.stop()
assert(#W.runtime.writes==0,'the probe writes nothing')
return 'ok'
''')

    def test_the_overlay_world_is_rendered_from_the_render_callback_and_released(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
local C=probe.controller()
assert(C.toggle_overlay():find('needs the probe drawn first',1,true))
tick(4)
local world=require('hd2runtime/runtime/event_world').open()
local cards=assert(probe.cards(world,selector.screen(world)))
local before=#calls
assert(C.toggle_overlay()=='overlay world created',table.concat(logged,' | '))
local names={}
for k=before+1,#calls do names[#names+1]=calls[k].name end
assert(table.concat(names,','):find('new_world,create_viewport,create_shading_environment,spawn_unit,camera,'
    ..'create_screen_gui,rect,text,rect',1,true),table.concat(names,','))
local gui
for k=before+1,#calls do if calls[k].name=='create_screen_gui'then gui=k;assert(calls[k].args[1]==NEW)end end
local green=rects_in(gui)
assert(#green==2 and green[1].args[4][2]==0 and green[1].args[4][3]==230 and green[1].args[4][4]==60 and near(at(green[2])[1],cards[1].rect.x))
assert(count('overlay world created: worlds()[2] of 2, viewport overlay')==1)
-- The engine's render callback: the original first, its results kept, then the world queued.
assert(rawget(_G,'render')~=ORIGINAL_RENDER)
local a,b=render(7)
assert(a=='original'and b==7)
local r=calls[#calls]
assert(r.name=='render_world'and r.args[1]==NEW)
render();render()
assert(called('render_world')==3)
-- F6 again: the callback restored, the GUI, viewport, shading environment and world released.
assert(C.toggle_overlay()=='overlay world released')
assert(rawget(_G,'render')==ORIGINAL_RENDER and #alive==1 and count('overlay world released (F6) after 3 renders')==1)
render()
assert(called('render_world')==3)
-- Movement and the timeout release it too.
C.toggle_overlay()
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=100})
tick(1)
assert(rawget(_G,'render')==ORIGINAL_RENDER and count('overlay world released (the grid moved)')==1)
tick(4)
C.toggle_overlay()
tick(40,1)
assert(rawget(_G,'render')==ORIGINAL_RENDER and count('overlay world released (timeout)')==1)
-- Another chain installed after ours: not undone, but our part stops queueing.
C.toggle_overlay()
local ours=rawget(_G,'render')
local other=function(...)return ours(...)end
rawset(_G,'render',other)
local renders=called('render_world')
C.toggle_overlay()
assert(rawget(_G,'render')==other)
render()
assert(called('render_world')==renders)
rawset(_G,'render',ORIGINAL_RENDER)
-- Refusals before anything is made: no render callback, the camera unit not loaded.
rawset(_G,'render',nil)
local made=called('new_world')
assert(C.toggle_overlay():find('the engine render callback is not a Lua function (nil)',1,true))
rawset(_G,'render',ORIGINAL_RENDER)
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT}})
assert(C.toggle_overlay():find('the camera unit or the shading environment is not loaded',1,true))
assert(called('new_world')==made)
-- The grid closing releases everything.
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT},units={RENDER.cameraUnit},
    shading={RENDER.shading}})
C.toggle_overlay()
SCREEN.close()
tick(2)
assert(rawget(_G,'render')==ORIGINAL_RENDER and #alive==1 and count('overlay world released (the loadout screen closed)')==1,table.concat(logged,' | '))
C.stop()
assert(#W.runtime.writes==0)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
