"""The Runtime-owned CUSTOM STRATAGEMS panel (development; docs/custom-stratagems.md, "A Runtime-owned custom stratagems
panel"; runtime/custom_stratagem_panel.lua). 0.3.0: the compact grid sits to the RIGHT of the native details panel
(stratagem_selector.details, ui+0x24B520, 1024 x 400 units), in its vertical band, never meeting it or the native list;
three columns kept by shrinking tiles first; the tooltip beside or below the panel; development icon diagnostics with
positive controls (a vanilla font material by name, a vanilla icon material by IdString64, the custom material by name
and by hash). The 0.1.0 renderer is kept as the legacy renderer and fallback (it too may never meet the details panel).
The panel exists only while a native stratagem selector is open. Phase 1 only draws; phase 2 is an option. Offline: the
event world with a loadout screen, a native grid and a details panel, the Runtime images and the engine font loaded, and
the recording stand-in engine GUI with the engine's own types and returns."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

PANEL = r"""
local panel=require('hd2runtime/runtime/custom_stratagem_panel')
local function at(c)return c.name=='rect'and c.args[2]or c.name=='text'and c.args[6]or c.name=='bitmap'and c.args[3]end
local function of(name)local out={};for _,c in ipairs(calls)do if c.name==name then out[#out+1]=c end end;return out end
local function texts_drawn()local out={};for _,c in ipairs(of('text'))do out[#out+1]=c.args[2]end;return out end
local function inside(a,b)return a.x>=b.x-0.5 and a.y>=b.y-0.5 and a.x+a.w<=b.x+b.w+0.5 and a.y+a.h<=b.y+b.h+0.5 end
local function meets(a,b)return a.x<b.x+b.w and b.x<a.x+a.w and a.y<b.y+b.h and b.y<a.y+a.h end
local function gui_calls(gui,name)local out={};for _,c in ipairs(calls)do if c.name==name and c.args[1]==gui then out[#out+1]=c end end;return out end
local function guis()local out={};for k,c in ipairs(calls)do if c.name=='create_screen_gui'then out[#out+1]=k end end;return out end
local function rect_of(c)return {x=at(c)[1],y=at(c)[2],w=c.args[3][1],h=c.args[3][2]}end
local ROWS,SECTIONS={4,4,4,4,4,4,4,4,4,2},{0,4,7}
-- IdString64.from_hex as the engine's: a tagged id (here a table) for Gui.bitmap (exe 0x3D3410).
engine.IdString64={from_hex=function(h)calls[#calls+1]={name='from_hex',args={h}};return {kind='IdString64',hex=h}end}
-- Gui.material returns the GUI's own instance (exe 0x3E7F00; here a table naming the GUI and the material); a material
-- the engine did not find comes back as a NULL light userdata (NULL below). Material.set_vector4 and
-- Quaternion.from_elements as the engine's (recorded; set_vector4 returns nothing).
local NULL=newproxy(true);getmetatable(NULL).__tostring=function()return'userdata: NULL'end
local function instance_of(gui,m)return {kind='Material',gui=gui,material=type(m)=='table'and m.hex or m}end
engine.Gui.material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return instance_of(gui,m)end
engine.Material={set_vector4=function(...)calls[#calls+1]={name='set_vector4',args={...}}end}
engine.Quaternion={from_elements=function(x,y,z,w)return {kind='Quaternion',x,y,z,w}end}
-- The Ui World, where the panel's GUIs are opened (0.7.0: the slot overlay's proven technique): named by the game
-- context, second in the engine's world array and in Application.worlds (full userdata, matched by position).
local OV=SEL.slotOverlay
local CONTEXT=(function()local s=W.read(W.GAME+OV.gameContext,8);local lo,hi=0,0
    for i=4,1,-1 do lo=lo*256+s:byte(i);hi=hi*256+s:byte(i+4)end;return lo+hi*4294967296 end)()
local UI_WORLD=0x24A97280080
W.write(CONTEXT+OV.uiWorld,W.u32(UI_WORLD%4294967296)..W.u32(math.floor(UI_WORLD/4294967296)))
W.engine_worlds({0x24A96260080,UI_WORLD})
local UW=newproxy(true);getmetatable(UW).__tostring=function()return'userdata: UiWorld'end
alive[2]=UW
local NATIVE_COLOURS='c0 (0.800, 1.000, 0.431, 0.357), c1 (1.000, 1.000, 1.000, 0.933), c2 (0.200, 0.000, 0.000, 0.000), '
    ..'c3 (0.000, 0.000, 0.000, 0.000)'
-- A 1080p loadout screen as the game lays it out at 1 px per unit: the list frame on the left, the details panel in the
-- middle (500..1524 x 232..632).
local function screen_1080(spec)
    spec=spec or{}
    SCREEN=W.loadout_screen({entries=spec.entries or{{type=136}},editedSlot=spec.slot or 0,selecting=spec.selecting})
    W.native_grid(SCREEN,{rows=spec.rows or ROWS,sections=spec.sections or SECTIONS,scroll=0,scale=1,frame={x=75,y=104}})
    return W.native_details(SCREEN,{x=spec.dx or 500,y=spec.dy or 232,scale=1})
end
"""


def lua(body):
    return run(WORLD + SELECT + PANEL + body)


class CustomStratagemPanelTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_legacy_layout_is_unchanged(self):
        self.check(r"""
-- 1080p: one native unit per pixel. The safe box is x 0.67 W, top 0.16 H below the screen top, 0.29 W x 0.15 H.
local L=assert(panel.layout(1920,1080))
assert(L.box.x==1286 and L.box.w==556 and L.box.h==162 and L.box.y==745 and near(L.unit,1)and not L.compact)
assert(inside(L.panel,L.box)and inside(L.panel,{x=0,y=0,w=1920,h=1080}))
assert(near(L.panel.h,120)and near(L.panel.y,787)and near(L.panel.w,556))
local t=L.tiles[1]
assert(t.visible and t.column==0 and t.row==0 and near(t.rect.w,80)and near(t.rect.h,80),'a native-sized square tile')
assert(near(t.rect.x,1294)and near(t.rect.y,795)and near(L.pitch,85))
assert(near(L.description.x,1552)and near(L.description.w,282)and near(L.description.h,80))
assert(L.grid.columns==3 and L.grid.rows==1 and L.grid.totalRows==1)
assert(near(L.title.size,13)and near(L.sizes.name,12)and near(L.sizes.text,9))
-- 4K: everything twice as large (the native card is 2 px/unit there), in the same place relative to the screen.
local K=assert(panel.layout(3840,2160))
assert(near(K.unit,2)and near(K.card,160)and near(K.pitch,170)and inside(K.panel,K.box))
assert(math.abs(K.panel.x-2*L.panel.x)<=2 and math.abs(K.panel.h-2*L.panel.h)<=2 and math.abs(K.tiles[1].rect.x-2*t.rect.x)<=2)
assert(math.abs(K.panel.y+K.panel.h-2*(L.panel.y+L.panel.h))<=2,'the same top, relative to the screen')
-- 1440p and 720p fit without shrinking.
for _,r in ipairs({{2560,1440},{1280,720},{1600,900}})do
    local X=assert(panel.layout(r[1],r[2]),r[1])
    assert(near(X.unit,r[2]/1080)and not X.compact and inside(X.panel,X.box)and X.description.w>0)
end
-- The native card's own scale sizes it when known; a scale too large for the box makes it compact, never larger.
local N=assert(panel.layout(3840,2160,{unit=2.4}))
assert(near(N.unit,2.4)and not N.compact)
local C=assert(panel.layout(3840,2160,{unit=3}))
assert(C.compact and C.unit<3 and inside(C.panel,C.box)and near(C.panel.h,C.box.h))
-- Unsupported: tiny screens, invalid units and counts.
assert(select(2,panel.layout(320,240))=='unsupported resolution'and select(2,panel.layout(1920,1080,{unit=0}))=='invalid unit')
assert(select(2,panel.layout(1920,1080,{count=61}))=='unsupported entry count')
-- Never over protected native UI: the native list frame on the left is clear; a rectangle in the box refuses.
assert(panel.layout(1920,1080,{protected={{x=500,y=166,w=395,h=528}}}))
assert(select(2,panel.layout(1920,1080,{protected={{x=1500,y=800,w=50,h=50}}}))=='the panel would meet protected native UI')
-- Future entries: three columns, one visible row in this box, later rows by scrolling; empty cells are not tiles.
local F=assert(panel.layout(1920,1080,{count=5}))
assert(F.grid.totalRows==2 and F.grid.rows==1 and #F.tiles==5)
assert(F.tiles[3].visible and F.tiles[3].column==2 and not F.tiles[4].visible and F.tiles[4].row==1)
local S=assert(panel.layout(1920,1080,{count=5,scroll=1}))
assert(not S.tiles[1].visible and S.tiles[4].visible and near(S.tiles[4].rect.y,F.tiles[1].rect.y)and S.grid.scroll==1)
assert(assert(panel.layout(1920,1080,{count=7,scroll=9})).grid.scroll==2,'the scroll is clamped')
for i=1,3 do for j=i+1,3 do assert(not meets(F.tiles[i].rect,F.tiles[j].rect))end end
-- The description wraps on words, at most the given lines.
local w=panel.wrap('Calls down a barrage of gas shells.',16,2)
assert(#w==2 and w[1]=='Calls down a'and w[2]=='barrage of gas shells.'or(w[2]:sub(-3)=='...'),table.concat(w,'|'))
assert(#panel.wrap('Calls down a barrage of gas shells.',40,3)==1)
return 'ok'
""")

    def test_the_0_2_0_box_layout_is_unchanged(self):
        self.check(r"""
-- 4K: 2 px per native unit; 60-unit tiles (120 px), a 64-unit pitch, the panel wrapping only the title and the grid.
local K=assert(panel.compact_layout(3840,2160,{count=6}))
assert(near(K.unit,2)and near(K.tile,120)and near(K.pitch,128)and not K.compact)
assert(K.box.x==2572 and near(K.panel.x,2572)and near(K.panel.w,408)and near(K.panel.h,324))
assert(near(K.footprint.w,764)and inside(K.footprint,K.box)and inside(K.panel,K.box),'the panel and the tooltip side fit')
assert(K.grid.columns==3 and K.grid.rows==2 and K.grid.totalRows==2)
-- Six entries: [1][2][3] over [4][5][6], none overlapping, all inside the panel.
for i=1,6 do
    local t=K.tiles[i]
    assert(t.visible and t.column==(i-1)%3 and t.row==math.floor((i-1)/3)and inside(t.rect,K.panel))
    for j=i+1,6 do assert(not meets(t.rect,K.tiles[j].rect))end
end
assert(near(K.tiles[2].rect.x-K.tiles[1].rect.x,128)and near(K.tiles[1].rect.y-K.tiles[4].rect.y,128))
-- 1080p and 1440p: the same layout at 1 and 4/3 px per unit (tiles 60 and 80 px), exactly proportional.
local L=assert(panel.compact_layout(1920,1080,{count=6}))
assert(near(L.unit,1)and near(L.tile,60)and near(L.panel.w,204)and near(L.panel.h,162)and near(L.footprint.w,382))
local Q=assert(panel.compact_layout(2560,1440,{count=6}))
assert(near(Q.tile,80)and near(Q.panel.h,216)and inside(Q.footprint,Q.box))
assert(math.abs(K.panel.x-2*L.panel.x)<=2 and near(K.tile,2*L.tile)and near(K.panel.h,2*L.panel.h))
-- The tooltip: right of the panel, level with the focused tile's top, inside the side area.
for _,index in ipairs({1,3,4,6})do
    local tip=panel.tooltip_rect(K,index,2)
    assert(tip and inside(tip,K.side)and tip.x>=K.panel.x+K.panel.w and not meets(tip,K.panel))
    local t=K.tiles[index].rect
    assert(near(tip.y+tip.h,math.min(t.y+t.h,K.side.y+K.side.h))or tip.y==K.side.y)
end
-- Nine entries: three rows, two in view; scrolling (prepared, not used by the proof) brings the third into view.
local N=assert(panel.compact_layout(3840,2160,{count=9}))
assert(N.grid.totalRows==3 and N.grid.rows==2 and N.tiles[7].visible==false)
local S=assert(panel.compact_layout(3840,2160,{count=9,scroll=1}))
assert(S.tiles[7].visible and not S.tiles[1].visible and near(S.tiles[7].rect.y,N.tiles[4].rect.y)
    and near(S.tiles[4].rect.y,N.tiles[1].rect.y),'rows 2 and 3 in view')
-- One entry: one row; the panel shrinks to it.
local O=assert(panel.compact_layout(1920,1080,{count=1}))
assert(O.grid.rows==1 and near(O.panel.h,(8+16+6+60+8)))
-- A native scale too large for the safe box: compact (smaller), never outside it.
local C=assert(panel.compact_layout(3840,2160,{count=6,unit=3}))
assert(C.compact and C.unit<3 and inside(C.footprint,C.box))
-- Never meeting protected native UI (the native list frame on the left is clear; anything in the footprint refuses).
assert(panel.compact_layout(3840,2160,{count=6,protected={{x=150,y=208,w=790,h=1056}}}))
assert(select(2,panel.compact_layout(3840,2160,{count=6,protected={{x=3200,y=1700,w=20,h=20}}}))
    =='the compact panel would meet protected native UI')
assert(select(2,panel.compact_layout(320,240))=='unsupported resolution'and select(2,panel.compact_layout(1920,1080,
    {count=0}))=='unsupported entry count')
-- The placeholders: purely visual entries.
local P=panel.placeholders(5)
assert(#P==5 and P[1].name=='Placeholder Custom Stratagem 2'and P[5].name=='Placeholder Custom Stratagem 6'
    and P[1].placeholder and P[1].icon==nil)
return 'ok'
""")

    def test_the_native_details_panel_is_read_and_checked(self):
        self.check(r"""
local d=screen_1080()
local world=require('hd2runtime/runtime/event_world').open()
local view=selector.screen(world)
local got=assert(selector.details(world,view))
assert(near(got.rect.x,500)and near(got.rect.y,232)and near(got.rect.w,1024)and near(got.rect.h,400)and near(got.scale,1))
assert(got.units.w==1024 and got.units.h==400)
-- Another layout (not the stratagem one), an uneven scale, no open selection: refused.
W.native_details(SCREEN,{x=500,y=232,scale=1,units={800,400}})
assert(select(2,selector.details(world,selector.screen(world))):find('not the stratagem layout',1,true))
W.native_details(SCREEN,{x=500,y=232,scale=1,scaleY=1.2})
assert(select(2,selector.details(world,selector.screen(world)))=='the details panel is not uniformly scaled')
W.native_details(SCREEN,{x=500,y=232,scale=1})
SCREEN.set('selecting',false)
assert(select(2,selector.details(world,selector.screen(world)))=='no stratagem selection is open')
assert(#W.runtime.writes==0)
return 'ok'
""")

    def test_the_panel_sits_right_of_the_native_details_panel_and_scales(self):
        self.check(r"""
-- 1080p: the details panel 500..1524 x 232..632; the column from 1539 (15 px margin) to 1905, in that band.
local D1={x=500,y=232,w=1024,h=400}
local L=assert(panel.anchored_layout(1920,1080,{details=D1,count=6}))
assert(near(L.column.x,1539)and near(L.column.w,366)and near(L.column.y,232)and near(L.column.h,400))
-- The tiles are 75 units (a quarter larger than 0.2.0's 60), 80 apart: the panel 8 + 3 x 75 + 2 x 5 + 8 = 251 wide.
assert(near(L.unit,1)and near(L.tile,75)and near(L.pitch,80)and L.grid.columns==3 and L.grid.rows==2 and not L.compact)
assert(near(L.panel.x,1539)and near(L.panel.y+L.panel.h,632)and near(L.panel.w,251)and near(L.panel.h,193))
assert(not meets(L.panel,D1)and L.panel.x-(D1.x+D1.w)>=15-1e-6,'clear of the details panel by the margin')
assert(L.panel.x+L.panel.w<=1920-15+1e-6 and inside(L.panel,L.column))
-- The tooltip does not fit beside it (109 px), so it goes below, inside the column.
assert(L.tooltipMode=='below'and inside(L.tooltipArea,L.column)and not meets(L.tooltipArea,L.panel))
for _,i in ipairs({1,3,6})do
    local tip=assert(panel.tooltip_rect(L,i,2,1))
    assert(inside(tip,L.column)and not meets(tip,L.panel)and not meets(tip,D1)and near(tip.y+tip.h,L.tooltipArea.y+L.tooltipArea.h))
end
for i=1,6 do assert(L.tiles[i].visible and inside(L.tiles[i].rect,L.panel))end
-- 4K: the details panel 1002..3050 x 600..1400 at 2 px/unit: the column from 3080 to 3810 (30 px margins), 150 px tiles.
local D4={x=1002,y=600,w=2048,h=800}
local K=assert(panel.anchored_layout(3840,2160,{details=D4,count=6,unit=2}))
assert(near(K.column.x,3080)and near(K.column.w,730)and near(K.tile,150)and near(K.panel.w,502)and near(K.panel.h,386))
assert(near(K.panel.y+K.panel.h,1400)and K.tooltipMode=='below'and not meets(K.panel,D4))
-- Exactly proportional between the two.
assert(near(K.tile,2*L.tile)and near(K.panel.w,2*L.panel.w)and near(K.column.x-(D4.x+D4.w),2*(L.column.x-(D1.x+D1.w))))
-- 1440p.
local Q=assert(panel.anchored_layout(2560,1440,{details={x=668,y=400,w=1365.3,h=533.3},count=6}))
assert(near(Q.tile,100)and Q.grid.columns==3 and inside(Q.panel,Q.column))
-- A wide column: the tooltip fits beside the panel.
local W1=assert(panel.anchored_layout(1920,1080,{details={x=300,y=232,w=1024,h=400},count=6}))
assert(W1.tooltipMode=='right'and not meets(W1.tooltipArea,W1.panel)and inside(W1.tooltipArea,W1.column))
-- A narrow column: the tiles shrink first and the three columns stay.
local N=assert(panel.anchored_layout(1920,1080,{details={x=700,y=232,w=1024,h=400},count=6}))
assert(N.grid.columns==3 and N.compact and N.tile<75 and N.tile>=36 and N.columnsDropped==0 and inside(N.panel,N.column))
-- Narrower: below the minimum tile, one column is dropped (two columns, three rows, two in view).
local M2=assert(panel.anchored_layout(1920,1080,{details={x=780,y=232,w=1024,h=400},count=6}))
assert(M2.grid.columns==2 and M2.columnsDropped==1 and M2.tile>=36 and M2.grid.totalRows==3 and M2.grid.rows==2)
-- No room at all, an unknown details panel, the native list protected.
assert(select(2,panel.anchored_layout(1920,1080,{details={x=890,y=232,w=1024,h=400},count=6}))
    =='no room right of the native details panel')
assert(select(2,panel.anchored_layout(1920,1080,{count=6}))=='the native details panel is unknown')
assert(select(2,panel.anchored_layout(1920,1080,{details=D1,count=6,protected={{x=1600,y=500,w=10,h=10}}}))
    =='the compact panel would meet protected native UI')
assert(panel.anchored_layout(1920,1080,{details=D1,count=6,protected={{x=75,y=104,w=395,h=528}}}))
return 'ok'
""")

    def test_the_panel_exists_only_while_a_stratagem_selector_is_open(self):
        self.check(r"""
screen_1080({entries={{type=136},{type=22}},slot=-1,selecting=false})
local P=panel.panel({placeholders=5,focus=true})
tick(6)
assert(not P.shown and called('create_screen_gui')==0,'not while the loadout screen is open')
SCREEN.set('editedSlot',1)
tick(6)
assert(not P.shown and called('create_screen_gui')==0)
SCREEN.set('selecting',true)
tick(1)
assert(not P.shown)
tick(2)
assert(P.shown and P.renderer=='compact'and called('create_screen_gui')==1,table.concat(logged,' | '))
assert(count('custom stratagem panel shown: active selector slot 1 (the selector opened; compact renderer)')==1)
assert(count('right of the native details panel 500, 232, 1024 x 400')==1,table.concat(logged,' | '))
SCREEN.set('editedSlot',2)
tick(2)
assert(P.shown and called('create_screen_gui')==1 and count('active selector slot 2 (was 1)')==1)
P.focus_next()
SCREEN.set('selecting',false)
tick(1)
assert(not P.shown and called('destroy_gui')==called('create_screen_gui')and count('hidden: selector closed')==1)
tick(6)
assert(not P.shown)
SCREEN.set('subState',5)
SCREEN.set('selecting',true)
tick(6)
assert(not P.shown,'not for a booster slot')
SCREEN.set('subState',10)
SCREEN.set('editedSlot',3)
tick(4)
assert(P.shown and P.focus==nil and count('shown: active selector slot 3')==1)
-- The details panel moves (it animates in): the panel follows it.
W.native_details(SCREEN,{x=480,y=232,scale=1})
tick(5)
assert(count('shown: active selector slot 3 (the details panel moved')==1 and near(P.layout.column.x,1519))
SCREEN.close()
tick(1)
assert(not P.shown and called('destroy_gui')==called('create_screen_gui'))
P.stop()
assert(#W.runtime.writes==0)
return 'ok'
""")

    def test_six_tiles_the_icon_logs_and_a_tooltip_below_the_panel(self):
        self.check(r"""
local D1=screen_1080()
local P=panel.panel({placeholders=5,focus=true})
tick(4)
assert(P.shown and P.renderer=='compact',table.concat(logged,' | '))
local L=P.layout
local g=guis()[1]
assert(near(L.unit,1)and near(L.tile,75)and not meets(L.panel,D1)and not meets(L.panel,{x=75,y=104,w=395,h=528}))
assert(calls[g].args[1]==UW,'the panel GUI is a screen GUI of the Ui World (the slot overlay technique)')
assert(#gui_calls(g,'rect')==1+4+6*(1+4+4)+1,'the panel, the tiles and one plate under the one icon')
local b=gui_calls(g,'bitmap')
assert(#b==1 and b[1].args[2]==images.material_name(ICON),'the Runtime icon material by name')
assert(b[1].args[3][3]==panel.LAYER_BASE+16,'the icon in the overlay band')
-- The icon on the native icon background's opaque plate: exactly its quad, one layer below, the native grey (36).
local plate
for _,c in ipairs(gui_calls(g,'rect'))do if c.args[2][3]==b[1].args[3][3]-1 then plate=c end end
assert(plate and plate.args[2][1]==b[1].args[3][1]and plate.args[2][2]==b[1].args[3][2]
    and plate.args[3][1]==b[1].args[4][1]and plate.args[3][2]==b[1].args[4][2],'the plate on the icon quad')
assert(plate.args[4][1]==255 and plate.args[4][2]==36 and plate.args[4][3]==36 and plate.args[4][4]==36)
-- The tiles are opaque: nothing behind a tile shows through the icon's transparent parts.
for _,c in ipairs(gui_calls(g,'rect'))do
    if c.args[2][3]==panel.LAYER_BASE+12 then assert(c.args[4][1]==255,'an opaque tile')end
end
for _,c in ipairs(gui_calls(g,'rect'))do assert(inside(rect_of(c),L.panel))end
-- The icon draw is logged: attempted, then succeeded with the engine's id.
assert(count('custom icon GUI bitmap draw attempted: Gui.bitmap("'..images.material_name(ICON)..'"')==1,
    table.concat(logged,' | '))
assert(count('custom icon GUI bitmap draw succeeded for orbital_gas_barrage (engine id')==1)
-- The icon shader's mask colours on this GUI's own instance of the icon material, as the native loadout slot sets them.
assert(count("custom icon colours set for orbital_gas_barrage on this GUI's material instance (the native loadout slot's "
    ..'values, colour set 0): '..NATIVE_COLOURS)==1,table.concat(logged,' | '))
local sv=gui_calls(g,'gui_material')
assert(#sv==1 and sv[1].args[2]==images.material_name(ICON))
local sets=of('set_vector4')
assert(#sets==4 and sets[1].args[1].gui==g and sets[1].args[1].material==images.material_name(ICON))
assert(sets[1].args[2]=='c0'and sets[2].args[2]=='c1'and sets[3].args[2]=='c2'and sets[4].args[2]=='c3')
assert(sets[1].args[3].kind=='Quaternion'and near(sets[1].args[3][1],0.8)and near(sets[1].args[3][2],1)
    and near(sets[2].args[3][4],0.93333334)and near(sets[3].args[3][1],0.2)and sets[4].args[3][1]==0)
-- F6: the tooltip below the panel, inside the column, the brackets on the tile.
assert(P.focus_next()=='focused orbital_gas_barrage')
local f=guis()[2]
local rects=gui_calls(f,'rect')
local tip=rect_of(rects[9])
assert(inside(tip,L.column)and not meets(tip,L.panel)and not meets(tip,D1)and tip.y+tip.h<=L.panel.y)
local words={}
for _,c in ipairs(gui_calls(f,'text'))do words[#words+1]=c.args[2]end
assert(words[1]=='Orbital Gas Barrage'and table.concat(words,' ',2)=='Calls down a barrage of gas shells.',
    table.concat(words,'|'))
assert(P.clear_focus()=='focus cleared')
-- F8: the icon diagnostics below the panel: row 1 (and D) in a GUI whose icon material instances get the native
-- colours, row 2 the same materials in a second GUI with nothing set.
assert(P.toggle_icon_test()=='icon diagnostics on',table.concat(logged,' | '))
local all=guis()
local dg,plain=all[#all-1],all[#all]
local bm=gui_calls(dg,'bitmap')
-- Row 1: A font by name; A vanilla not resident in this fixture (not drawn); B by name and by hash (IdString64.from_hex
-- of its name hash); E no test pattern in this test; C the texture (never a bitmap); D the custom material at four sizes.
local hi,lo=images.hash(images.material_name(ICON))
assert(#bm==7 and bm[1].args[2]==FONT and bm[2].args[2]==images.material_name(ICON)and bm[3].args[2].kind=='IdString64'
    and bm[3].args[2].hex==('%08x%08x'):format(hi,lo),#bm)
local sizes={}
for k=4,7 do assert(bm[k].args[2]==images.material_name(ICON));sizes[#sizes+1]=bm[k].args[4][1]end
assert(sizes[1]<sizes[2]and sizes[2]<sizes[3]and sizes[3]<sizes[4],'four sizes, smallest first')
-- Row 2: B by name only (A vanilla not resident, no pattern); nothing set on the plain GUI.
local pb=gui_calls(plain,'bitmap')
assert(#pb==1 and pb[1].args[2]==images.material_name(ICON)and#gui_calls(plain,'gui_material')==0)
local coloured_sets=0
for _,c in ipairs(of('set_vector4'))do if c.args[1].gui==dg then coloured_sets=coloured_sets+1 end end
assert(coloured_sets==8,'c0-c3 on the custom material, once by name and once by hash: '..coloured_sets)
assert(count('icon diagnostics colours (row 1 and D): '..NATIVE_COLOURS)==1)
-- (each line: the label, the cell size, then the resource and its facts)
local function lines_with(a,b)
    local n=0
    for _,line in ipairs(logged)do if line:find(a,1,true)and line:find(b,1,true)then n=n+1 end end
    return n
end
assert(lines_with('icon diagnostics A vanilla at ','px: resource 0x9C9B3DCE316F1256; material NOT loaded')==1,
    table.concat(logged,' | '))
assert(lines_with('icon diagnostics A vanilla plain at ','px: resource 0x9C9B3DCE316F1256; material NOT loaded')==1)
assert(count('Gui.bitmap not created: not drawn: the material is not loaded')==2)
assert(lines_with('icon diagnostics C texture at ','px: resource '..images.material_name(ICON)..'; material loaded, '
    ..'texture loaded')==1 and count('not created: not drawable: Gui.bitmap takes a material, not a texture')==1)
assert(lines_with('icon diagnostics B name at ','px: resource '..images.material_name(ICON)..'; material loaded, texture '
    ..'loaded, shader ')==1 and count('Gui.bitmap created (engine id')>=7 and count('update: not used (retained bitmap)')==13)
assert(count("Gui.bitmap created (engine id")>=1 and count("colours set on this GUI's instance")>=6
    and count('colours none (plain GUI)')==1 and count('colours none (its own shader)')==1)
assert(count('custom icon loaded: texture '..images.material_name(ICON)..' loaded')==1)
assert(count('custom icon GUI material loaded: '..images.material_name(ICON)..' loaded, exact true')==1)
for _,c in ipairs(gui_calls(dg,'rect'))do assert(inside(rect_of(c),L.diagArea)and not meets(rect_of(c),D1))end
assert(P.toggle_icon_test()=='icon diagnostics off')
-- With the vanilla icon material resident, it is drawn by hash too.
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT,{hash='0x9C9B3DCE316F1256'}},fonts={FONT}})
P.toggle_icon_test()
all=guis()
dg,plain=all[#all-1],all[#all]
bm=gui_calls(dg,'bitmap')
assert(#bm==8 and bm[2].args[2].hex=='9c9b3dce316f1256',#bm)
assert(#gui_calls(plain,'bitmap')==2 and gui_calls(plain,'bitmap')[1].args[2].hex=='9c9b3dce316f1256')
P.toggle_icon_test()
assert(P.press():find('not enabled',1,true))
SCREEN.set('selecting',false)
tick(1)
assert(called('destroy_gui')==called('create_screen_gui'))
P.stop()
assert(#W.runtime.writes==0 and W.read(settings.base,settings.size)==SETTINGS,'phase 1 writes nothing')
return 'ok'
""")

    def test_icon_colours_are_the_native_slot_values_and_a_missing_instance_is_never_used(self):
        self.check(r"""
local PATTERN=images.handle('icon_test_pattern',MOD)
local PATTERN_NAME=images.name(MOD,'icon_test_pattern')
W.icon_resources({textures={ICON_NAME,PATTERN_NAME},materials={ICON_NAME,PATTERN_NAME,FONT},fonts={FONT}})
local L=assert(panel.anchored_layout(1920,1080,{details={x=500,y=232,w=1024,h=400},count=6}))
-- The colours come from the game: the token's colour set (StratagemInfo +0xB8) indexes the category table.
local world=require('hd2runtime/runtime/event_world').open()
local vars,set=selector.icon_colours(world,118)
assert(set==0 and vars[1][1]=='c0'and near(vars[1][2],0.8)and near(vars[1][4],0.43137255)and vars[4][1]=='c3'
    and vars[4][2]==0)
W.write(ROW[118]+0xB8,W.u32(2))
vars,set=selector.icon_colours(world,118)
assert(set==2 and near(vars[1][3],0.34117648),'another colour set, another category colour')
W.write(ROW[118]+0xB8,W.u32(9))
assert(selector.icon_colours(world,118)==nil,'a colour set outside the table is refused')
W.write(ROW[118]+0xB8,W.u32(0))
-- The diagnostics with the test pattern: drawn coloured (row 1) and plain (row 2).
local lines={}
local dg,results=panel.draw_icon_diagnostics(W.runtime,L,ICON,function(l)lines[#lines+1]=l end,
    {colours=selector.icon_colours(world,118),pattern=PATTERN})
assert(dg)
local by={}
for _,r in ipairs(results)do by[r.label]=r end
assert(by['E pattern'].id and by['E pattern'].colours=="set on this GUI's instance",tostring(by['E pattern'].colours))
assert(by['E pattern plain'].id and by['E pattern plain'].colours=='none (plain GUI)')
assert(by['B name'].colours=="set on this GUI's instance"and by['A font'].colours=='none (its own shader)')
dg.close()
-- A material the engine did not find: Gui.material returns NULL; nothing reaches Material.set_vector4.
engine.Gui.material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return NULL end
local before=#of('set_vector4')
local entries=panel.entries()
entries[1].colours=vars
lines={}
local drawn=panel.draw_compact(W.runtime,L,entries,function(l)lines[#lines+1]=l end)
assert(drawn and#of('set_vector4')==before)
assert(table.concat(lines,' | '):find('custom icon colours NOT set for orbital_gas_barrage: the GUI has no instance of '
    ..'that material (not found) (the icon stays transparent)',1,true),table.concat(lines,' | '))
drawn.close()
engine.Gui.material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return instance_of(gui,m)end
assert(#W.runtime.writes==0 and W.read(settings.base,settings.size)==SETTINGS)
return 'ok'
""")

    def test_the_legacy_renderer_is_the_fallback_and_never_meets_the_details_panel(self):
        self.check(r"""
-- The compact layout refused: the legacy (0.1.0) renderer at its box (1286..1842 x 787..907) would meet the details
-- panel (here 500..1524 x 560..960): refused too.
screen_1080({dy=560})
local real=panel.anchored_layout
panel.anchored_layout=function()return nil,'refused for the test'end
local P=panel.panel({placeholders=5,focus=true})
tick(4)
assert(not P.shown and count('compact layout refused (refused for the test); falling back to the legacy renderer')>=1,
    table.concat(logged,' | '))
assert(count('not shown: the legacy renderer refused too: the panel would meet protected native UI')==1,
    table.concat(logged,' | '))
P.stop()
-- With the details panel clear of its box (further left), the legacy renderer draws, under the same lifecycle.
screen_1080({dx=100,dy=560})
P=panel.panel({placeholders=5,focus=true})
tick(4)
assert(P.shown and P.renderer=='legacy',table.concat(logged,' | '))
assert(#of('bitmap')==1 and find('text',2,'Orbital Gas Barrage'))
SCREEN.set('selecting',false)
tick(1)
assert(not P.shown and called('destroy_gui')==called('create_screen_gui'))
P.stop()
panel.anchored_layout=real
-- No readable details panel: nothing is drawn at all (its place is unknown).
screen_1080()
W.native_details(SCREEN,{x=500,y=232,scale=1,units={10,10}})
local Q=panel.panel({})
tick(4)
assert(not Q.shown and count('not shown: the native details panel: the details panel is 10.0 x 10.0 units')==1)
Q.stop()
assert(#W.runtime.writes==0)
return 'ok'
""")

    def test_drawing_refuses_before_anything_is_created(self):
        self.check(r"""
local L=assert(panel.anchored_layout(1920,1080,{details={x=500,y=232,w=1024,h=400},count=6}))
local entries=panel.entries()
for _,p in ipairs(panel.placeholders(5))do entries[#entries+1]=p end
-- An icon not loaded does not stop the panel: its tile gets the placeholder mark, logged.
W.icon_resources({textures={},materials={FONT},fonts={FONT}})
local lines={}
local drawn,why=panel.draw_compact(W.runtime,L,entries,function(l)lines[#lines+1]=l end)
assert(drawn and #of('bitmap')==0 and lines[1]:find('custom icon unavailable for orbital_gas_barrage',1,true),why)
local marks=0
for _,c in ipairs(of('text'))do if c.args[2]=='?'then marks=marks+1 end end
assert(marks==6,'six placeholder marks')
drawn.close()
-- The font not loaded: refused before anything is created.
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME}})
local made=called('create_screen_gui')
local none
none,why=panel.draw_compact(W.runtime,L,entries)
assert(none==nil and why:find('the engine font is not loaded',1,true)and called('create_screen_gui')==made)
-- A refused icon: logged as failed, the tile keeps its mark, the GUI stays.
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT}})
engine.Gui.bitmap=function(...)calls[#calls+1]={name='bitmap',args={...}}end
lines={}
local before=called('destroy_gui')
drawn,why=panel.draw_compact(W.runtime,L,entries,function(l)lines[#lines+1]=l end)
assert(drawn and called('destroy_gui')==before,why)
assert(lines[1]:find('custom icon GUI bitmap draw attempted',1,true)and lines[2]:find('custom icon GUI bitmap draw '
    ..'failed for orbital_gas_barrage: the engine returned no id; drawing the placeholder mark',1,true),table.concat(lines,' | '))
drawn.close()
-- The diagnostics keep going past refused controls (each is optional) and report them.
local dg,results=panel.draw_icon_diagnostics(W.runtime,L,ICON,function(l)lines[#lines+1]=l end)
assert(dg and #results==13,'six coloured controls, three plain and four sizes')
for _,r in ipairs(results)do
    if r.label=='C texture'then assert(r.reason:find('not drawable',1,true))
    elseif r.label:find('^E pattern')then assert(r.reason=='no test pattern image in this build',r.label)
    elseif r.label:find('^A vanilla')then assert(r.reason:find('not loaded',1,true),r.label)
    else assert(r.id==nil and r.reason=='the engine returned no id',r.label)end
end
dg.close()
assert(#W.runtime.writes==0)
return 'ok'
""")

    def test_phase_two_selection_writes_the_token_and_skips_placeholders(self):
        self.check(r"""
screen_1080({entries={{type=136},{type=22},{type=41}},slot=1,rows={4,4,2},sections={0}})
local selected
local P=panel.panel({placeholders=5,focus=true,selection=true,on_selected=function(h)selected=h end})
tick(4)
assert(P.shown and P.press()=='focused orbital_gas_barrage',table.concat(logged,' | '))
assert(P.press():find('selecting orbital_gas_barrage into slot 1',1,true))
local job=settle_job(P.handle)
assert(job.status=='selected'and job.index==1,tostring(job.code)..' '..tostring(job.reason))
assert(SCREEN.entry(1)==118 and SCREEN.widget(1)==118)
assert(selector.virtual_slots().slots[1].definition=='orbital_gas_barrage'and selected==job)
assert(P.cancel()=='restoring the slot')
assert(settle_job(P.handle).status=='restored')
tick(2)
assert(SCREEN.entry(1)==22 and selector.virtual_slots()==nil)
P.focus_next()
assert(P.focus==2 and P.press()=='placeholders cannot be selected')
assert(P.cancel()=='focus cleared')
assert(W.read(settings.base,settings.size)==SETTINGS)
P.stop()
return 'ok'
""")

    def test_one_continuous_selection_fills_every_slot_and_the_native_selector_closes_when_full(self):
        self.check(r"""
screen_1080({entries={},slot=0,rows={4,4,2},sections={0}})
local handles={}
local P=panel.panel({placeholders=5,focus=true,selection=true,on_selected=function(h)handles[#handles+1]=h end})
tick(4)
assert(P.shown,table.concat(logged,' | '))
local function u32_at(at)local s=W.read(at,4);return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216 end
local function edited()return u32_at(SCREEN.ui+SEL.loadout.editedSlot)end
local FO=SEL.slotFocus
local function highlight()return u32_at(SCREEN.panel+FO.focus)end
local function focused(k)return math.floor(SCREEN.widget_flags(k)/FO.focusedBit)%2==1 end
-- Orbital Gas Barrage three times: each fills the slot the selector is open for and moves the native selector on (the
-- highlight and the edited slot together, redrawn by the game); the panel stays open and follows it.
for slot=0,2 do
    assert(P.select_index(1,'F7'):find('into slot '..slot,1,true))
    local job=settle_job(P.handle)
    assert(job.status=='selected'and job.index==slot and job.advance.status=='advanced'and job.advance.verified,
        tostring(job.code)..' '..tostring(job.advance and job.advance.reason)..' | '..table.concat(logged,' | '))
    tick(2)
    assert(P.shown and edited()==slot+1,'the panel stays open for slot '..(slot+1))
    assert(highlight()==slot+1 and focused(slot+1)and not focused(slot)and not focused(0)==(slot+1~=0),
        'the native highlight is on slot '..(slot+1)..', not '..highlight())
    assert(W.read(SCREEN.ui+SEL.loadout.panel0Widgets+(slot+1)*SEL.loadout.widgetStride+FO.flash,1):byte()==0,
        'the game consumed the flash byte')
    assert(count('the native selector moved on to slot '..(slot+1)..' (the next empty slot): the native highlight and '
        ..'the edited slot; the panel stays open for it')==1,table.concat(logged,' | '))
    assert(count('active selector slot '..(slot+1)..' (was '..slot..')')==1,table.concat(logged,' | '))
end
-- From slot 1 on, the record write's repaint first put the highlight on slot 0 (its first bind), as the game does.
assert(SCREEN.first_binds==2,'first binds: '..tostring(SCREEN.first_binds))
-- The fourth fills the last empty slot: the native selector is closed as Back closes it (the picker-close sound, then
-- the game's own close handler with this loadout UI: one native call); the panel closes with it.
assert(#W.runtime.selector_closes==0,'no close while an empty slot was left')
assert(P.select_index(1,'F7'):find('into slot 3',1,true))
local job=settle_job(P.handle)
assert(job.status=='selected'and job.index==3 and job.advance.status=='closed'and job.advance.verified,
    tostring(job.advance.reason)..' | '..table.concat(logged,' | '))
assert(#W.runtime.selector_closes==1 and W.runtime.selector_closes[1].ui==SCREEN.ui and SCREEN.native_closes==1)
tick(1)
assert(not P.shown and count('the loadout is full: the native selector was closed as Back closes it (verified true)')==1,
    table.concat(logged,' | '))
assert(count('stratagem selector SELECTOR CLOSE VERIFIED: the native selector (open for slot 3) closed by the game\'s '
    ..'own close handler (game+146F3B0, the call Back makes) after the selection filled the loadout')==1)
-- The highlight is back on the slot the selector edited (the last one), not left on slot 0 by the repaint; the
-- selection was closed by the game's handler, never by a Runtime write of the selection byte.
assert(highlight()==3 and focused(3)and edited()==3,'highlight '..highlight())
for _,w in ipairs(W.runtime.writes)do assert(w.address~=SCREEN.ui+SEL.loadout.selectionOpen,'the selection byte written')end
assert(W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()==0)
tick(5)
assert(not P.shown,'the native selector stays closed')
for k=0,3 do assert(SCREEN.entry(k)==118)end
local set=selector.virtual_slots()
assert(set.slots[0]and set.slots[1]and set.slots[2]and set.slots[3],'four instances of one definition')
-- Reopened (to replace a slot), the panel shows again.
SCREEN.set('editedSlot',2)
SCREEN.set('selecting',true)
tick(4)
assert(P.shown,table.concat(logged,' | '))
-- Replacing slot 2 in the full loadout (it already holds the token): no write, it stays virtual; closed again.
local writes=#W.runtime.writes
assert(P.select_index(1,'F7'):find('into slot 2',1,true))
job=settle_job(P.handle)
assert(job.status=='selected'and not job.written and job.advance.status=='closed'and#W.runtime.selector_closes==2)
for k=writes+1,#W.runtime.writes do
    local a=W.runtime.writes[k].address
    assert(a<SCREEN.record or a>=SCREEN.record+SEL.loadout.recordStride,'no record write (it already held the token)')
end
tick(1)
assert(not P.shown and highlight()==2 and focused(2),'the highlight follows the edited slot 2')
assert(W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()==0)
-- The close is refused (nothing called) when the game no longer shows the selection the Runtime filled: the panel
-- then closes as before and the player closes the native selector with Back.
SCREEN.set('editedSlot',1)
SCREEN.set('selecting',true)
tick(4)
assert(P.shown)
W.write(SCREEN.ui+SEL.loadout.panelMode,W.u32(1))
assert(P.select_index(1,'F7'):find('into slot 1',1,true))
job=settle_job(P.handle)
assert(job.status=='selected'and job.advance.status=='full'and job.advance.close.code=='PANEL_MODE'
    and#W.runtime.selector_closes==2,tostring(job.advance.reason))
assert(count('SELECTOR CLOSE REFUSED (nothing called; the native selector stays open: close it with Back): PANEL_MODE')==1)
tick(1)
assert(not P.shown and count('close the native stratagem selector with Back')==1)
assert(W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()==1,'still open for the player\'s Back')
assert(#handles==6 and W.read(settings.base,settings.size)==SETTINGS)
P.stop()
return 'ok'
""")

    def test_the_mouse_is_read_converted_and_hit_tested(self):
        self.check(r"""
local input=require('hd2runtime/runtime/input')
local MOUSE={x=0,y=0,w=1920,h=1080,left=false,focused=true}
input.set_backend({focused=function()return MOUSE.focused end,down=function(code)return code==input.LBUTTON and MOUSE.left end,
    mouse=function()if not MOUSE.focused then return nil end;return MOUSE.x,MOUSE.y,MOUSE.w,MOUSE.h end})
MOUSE.x,MOUSE.y,MOUSE.left=100,200,true
local m=assert(input.mouse())
assert(m.x==100 and m.y==200 and m.w==1920 and m.h==1080 and m.left)
-- Client pixels (top-left origin) to GUI pixels (bottom-left origin), scaled to the GUI resolution.
local x,y=panel.to_gui(m,1920,1080)
assert(near(x,100)and near(y,880))
x,y=panel.to_gui({x=960,y=540,w=1920,h=1080},3840,2160)
assert(near(x,1920)and near(y,1080),'a 1080p client on a 4K GUI')
x,y=panel.to_gui({x=0,y=0,w=2560,h=1440},2560,1440)
assert(near(x,0)and near(y,1440),'the client top-left is the GUI top-left')
-- The game window without the focus, or a backend without a mouse: no mouse.
MOUSE.focused=false
assert(select(2,input.mouse())=='the game window does not have the focus')
input.set_backend({focused=function()return true end,down=function()return false end})
assert(select(2,input.mouse())=='no mouse in this input backend')
-- The hit test: the tile under a point, and whether it is in the panel.
local L=assert(panel.anchored_layout(1920,1080,{details={x=500,y=232,w=1024,h=400},count=6}))
local t1,t5=L.tiles[1].rect,L.tiles[5].rect
local i,inside_panel=panel.hit(L,t1.x+1,t1.y+1)
assert(i==1 and inside_panel)
i,inside_panel=panel.hit(L,t5.x+t5.w/2,t5.y+t5.h/2)
assert(i==5 and inside_panel)
i,inside_panel=panel.hit(L,t1.x+t1.w+1,t1.y+1)
assert(i==nil and inside_panel,'the gap between tiles is in the panel but on no tile')
i,inside_panel=panel.hit(L,10,10)
assert(i==nil and not inside_panel)
return 'ok'
""")

    def test_hover_focuses_and_a_click_selects_the_custom_card(self):
        self.check(r"""
local input=require('hd2runtime/runtime/input')
local MOUSE={x=0,y=0,w=1920,h=1080,left=false,focused=true}
input.set_backend({focused=function()return MOUSE.focused end,down=function(code)return code==input.LBUTTON and MOUSE.left end,
    mouse=function()if not MOUSE.focused then return nil end;return MOUSE.x,MOUSE.y,MOUSE.w,MOUSE.h end})
-- Points the cursor at a GUI rectangle's centre (the GUI is 1920 x 1080 like the client).
local function point_at(r)MOUSE.x,MOUSE.y=r.x+r.w/2,1080-(r.y+r.h/2)end
screen_1080({entries={{type=136},{type=22},{type=41}},slot=1,rows={4,4,2},sections={0}})
local selected
local P=panel.panel({placeholders=5,focus=true,selection=true,mouse=true,on_selected=function(h)selected=h end})
MOUSE.x,MOUSE.y=10,10
tick(4)
assert(P.shown,table.concat(logged,' | '))
local L=P.layout
-- Hover: the cursor over Orbital Gas Barrage focuses it (brackets and tooltip), nothing written.
point_at(L.tiles[1].rect)
tick(1)
assert(P.focus==1 and count('focused orbital_gas_barrage (tile 1)')==1 and #W.runtime.writes==0)
-- Leaving the tile clears the focus; over a placeholder focuses it.
MOUSE.x,MOUSE.y=10,10
tick(1)
assert(P.focus==nil)
point_at(L.tiles[2].rect)
tick(1)
assert(P.focus==2 and count('focused placeholder_2 (tile 2)')==1)
-- A click on a placeholder is refused; a click in the panel between tiles selects nothing; a click outside the
-- panel is not the panel's.
MOUSE.left=true;tick(1);MOUSE.left=false;tick(1)
assert(count('click on placeholder_2 refused: placeholders cannot be selected')==1 and #W.runtime.writes==0)
local t1=L.tiles[1].rect
MOUSE.x,MOUSE.y=t1.x+t1.w+1,1080-(t1.y+t1.h/2)
MOUSE.left=true;tick(1);MOUSE.left=false;tick(1)
assert(count('on no tile')==1 and #W.runtime.writes==0)
MOUSE.x,MOUSE.y=10,10
MOUSE.left=true;tick(1);MOUSE.left=false;tick(1)
assert(count('click at GUI')==2,'a click outside the panel is not logged')
-- Holding the button does not repeat the click.
point_at(L.tiles[1].rect)
MOUSE.left=true
tick(1)
assert(count('click: selecting orbital_gas_barrage (token Orbital Precision Strike) into slot 1')==1,table.concat(logged,' | '))
tick(3)
assert(count('click: selecting orbital_gas_barrage')==1,'held: one click')
MOUSE.left=false
local job=settle_job(P.handle)
assert(job.status=='selected'and job.index==1,tostring(job.code)..' '..tostring(job.reason))
-- The game's own repaint shows the token in slot 1; the virtual identity is recorded; the saved order reconstructs it.
assert(SCREEN.entry(1)==118 and SCREEN.widget(1)==118)
local set=selector.virtual_slots()
assert(set.slots[1].definition=='orbital_gas_barrage'and set.slots[1].token==PRECISION_ID and selected==job)
assert(count('SELECTED orbital_gas_barrage: slot 1 now holds Orbital Precision Strike; virtual slots: 1 = '
    ..'orbital_gas_barrage')==1)
assert(select(2,selector.reconstruct(set.pairs))==1)
-- Another slot changed natively: the identity follows the new order, and that order still reconstructs it.
W.write(SCREEN.record+0x188+2*0x30,W.u32(22))
SCREEN.frame()
tick(3)
set=selector.virtual_slots()
assert(set and set.slots[1]and selector.reconstruct(set.pairs)[1]=='orbital_gas_barrage')
-- The selector moved on to another slot before a click lands: refused, nothing written.
local writes=#W.runtime.writes
SCREEN.set('editedSlot',2)
tick(1)
P.select_index(1,'click')
assert(#W.runtime.writes==writes)
-- (the panel follows slot 2 a frame later; a stale slot is refused)
SCREEN.set('editedSlot',3)
assert(P.select_index(1,'click'):find('no longer open for slot 2',1,true))
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed')
P.stop()
return 'ok'
""")


# 0.7.0: the virtual slots' overlays (runtime/stratagem_slot_overlay.lua virtual_slots, started by the panel), driven by
# the real selections. Each slot's icon element and its native icon background (the grey box, widget + 0x110: a filled
# rectangle with its effective colour) are laid out as the game lays them: 70 x 70 px at (100 + 80 k, 900).
OVERLAYS = r"""
local O,E,LO=SEL.slotOverlay,SEL.grid.element,SEL.loadout
engine.Gui.update_bitmap=nothing('update_bitmap')
local function widget(k)return SCREEN.ui+LO.panel0Widgets+k*LO.widgetStride end
local function place(k)
    for _,e in ipairs({SCREEN.element(k),widget(k)+O.background})do
        W.write(e+E.size,W.f32(70)..W.f32(70))
        W.write(e+E.m00,W.f32(1));W.write(e+E.m02,W.f32(0));W.write(e+E.m20,W.f32(0));W.write(e+E.m22,W.f32(1))
        W.write(e+E.tx,W.f32(100+80*k));W.write(e+E.ty,W.f32(900))
    end
    W.write(SCREEN.element(k)+O.alpha,W.f32(1))
    local bg=widget(k)+O.background
    W.write(bg+O.primitive,W.u32(200+k))
    W.write(bg+O.effectiveColour,W.f32(1)..W.f32(36/255)..W.f32(36/255)..W.f32(36/255))
end
local function last_gui()local k;for i,c in ipairs(calls)do if c.name=='create_screen_gui'then k=i end end;return k end
-- The overlay GUI: the newest GUI holding a bitmap at the overlay layer.
local function overlay_gui()
    local k
    for i,c in ipairs(calls)do
        if c.name=='bitmap'and c.args[3][3]==O.overlayLayer then k=c.args[1]end
    end
    return k
end
local function alive_gui(g)
    for _,c in ipairs(calls)do if c.name=='destroy_gui'and c.args[2]==g then return false end end
    return g~=nil
end
-- The slots overlaid now: {[slot] = {bitmap, plate}} read from the live overlay GUI.
local function overlaid()
    local g=overlay_gui()
    local out={}
    if not alive_gui(g)then return out end
    for _,c in ipairs(gui_calls(g,'bitmap'))do
        local slot=math.floor((c.args[3][1]-100)/80+0.5)
        out[slot]={bitmap=c}
    end
    for _,c in ipairs(gui_calls(g,'rect'))do
        local slot=math.floor((c.args[2][1]-100)/80+0.5)
        if out[slot]then out[slot].plate=c end
    end
    return out
end
local function slots_of(set)local t={};for k=0,3 do t[#t+1]=set[k]and'V'or'n'end;return table.concat(t,' ')end
local function native_slot_bytes()
    local out={}
    for k=0,3 do out[k]=W.read(SCREEN.element(k),0x160)..W.read(widget(k)+O.background,0x118)end
    return out
end
local function select_into(P,slot)
    SCREEN.set('selecting',false);tick(1)
    SCREEN.set('editedSlot',slot);SCREEN.set('selecting',true);tick(4)
    assert(P.shown,'the panel for slot '..slot..': '..table.concat(logged,' | '))
    assert(P.select_index(1,'F7'):find('into slot '..slot,1,true))
    local job=settle_job(P.handle)
    assert(job.status=='selected'and job.index==slot,tostring(job.code)..' '..tostring(job.reason))
    tick(2)
    return job
end
"""


def overlays(body):
    return run(WORLD + SELECT + PANEL + OVERLAYS + body)


class VirtualSlotOverlayTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(overlays(body), b'ok')

    def test_virtual_native_virtual_native_then_four_instances_each_with_its_own_overlay(self):
        self.check(r"""
-- A full loadout: slot 1 holds a NATIVE Orbital Precision Strike (the token's own stratagem, picked natively).
screen_1080({entries={{type=136},{type=118},{type=41},{type=130}},slot=0,rows={4,4,2},sections={0}})
for k=0,3 do place(k)end
local before=native_slot_bytes()
local P=panel.panel({placeholders=5,focus=true,selection=true})
tick(4)
assert(P.shown and P.overlays,table.concat(logged,' | '))
assert(next(overlaid())==nil,'no virtual slot, no overlay')
-- Gas Barrage into slot 0 (replacing 136) and slot 2 (replacing 41): GAS / PRECISION / GAS / other.
select_into(P,0)
select_into(P,2)
assert(slots_of(selector.virtual_slots().slots)=='V n V n')
local o=overlaid()
assert(o[0]and not o[1]and o[2]and not o[3],'overlays on slots 0 and 2 only: '..table.concat(logged,' | '))
assert(SCREEN.widget(1)==118,'slot 1 is a native Precision Strike and gets no overlay')
local g=overlay_gui()
assert(calls[g].args[1]==UW,'the overlays are a Ui World GUI')
for _,slot in ipairs({0,2})do
    local b,pl=o[slot].bitmap,o[slot].plate
    assert(b.args[2]==images.material_name(ICON),'the definition\'s icon')
    assert(b.args[3][1]==100+80*slot and b.args[3][2]==900 and b.args[4][1]==70 and b.args[4][2]==70,'the icon quad')
    -- The plate: exactly the icon's quad, one layer below, opaque, the native background's live colour (36).
    assert(pl and pl.args[2][1]==b.args[3][1]and pl.args[2][2]==900 and pl.args[2][3]==O.overlayLayer-1
        and pl.args[3][1]==70 and pl.args[3][2]==70,'the plate on the icon quad')
    assert(pl.args[4][1]==255 and pl.args[4][2]==36 and pl.args[4][3]==36 and pl.args[4][4]==36,'opaque native grey')
end
assert(count('OVERLAY: 2 icons drawn over native slot icons (layer 940, on a backing plate, the native icons '
    ..'untouched): slot 0 (orbital_gas_barrage) at 100, 900, 70 x 70; slot 2 (orbital_gas_barrage) at 260, 900, 70 x '
    ..'70')>=1,table.concat(logged,' | '))
-- The same colour treatment as the panel's tile: the same c0-c3 on the overlay's and the panel's material instances.
local function vectors_of(gui)
    local out={}
    for _,c in ipairs(of('set_vector4'))do
        if c.args[1].gui==gui and c.args[1].material==images.material_name(ICON)then
            out[#out+1]=c.args[2]..'='..table.concat({c.args[3][1],c.args[3][2],c.args[3][3],c.args[3][4]},',')
        end
    end
    return table.concat(out,' ')
end
local panel_gui
for _,c in ipairs(of('bitmap'))do if c.args[3][3]==panel.LAYER_BASE+16 then panel_gui=c.args[1]end end
assert(panel_gui and vectors_of(g)~=''and vectors_of(g)==vectors_of(panel_gui),vectors_of(g)..' | '..vectors_of(panel_gui))
-- Slots 1 and 3 too: four instances of the one definition, four overlays.
select_into(P,1)
select_into(P,3)
o=overlaid()
assert(o[0]and o[1]and o[2]and o[3],'four overlays')
assert(slots_of(selector.virtual_slots().slots)=='V V V V')
-- Nothing Runtime-written touched a slot's icon element or its background, the StratagemInfo rows or a texture: the
-- only writes are the loadout record's entries and the slot focus (the advance).
for _,w in ipairs(W.runtime.writes)do
    for k=0,3 do
        assert(w.address<SCREEN.element(k)or w.address>=SCREEN.element(k)+0x160,'slot '..k..' icon element written')
        assert(w.address<widget(k)+O.background or w.address>=widget(k)+O.background+0x118,'slot '..k..' background written')
    end
end
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo write')
-- The native slot bytes: only the game's own repaint changed them (the type each slot shows), never the Runtime: the
-- background boxes are byte-identical and every icon element's material is the slot's own.
local after=native_slot_bytes()
for k=0,3 do
    assert(after[k]:sub(0x161)==before[k]:sub(0x161),'slot '..k..' background changed')
    assert(W.read(SCREEN.element(k)+SEL.slotIcon.material,8)==W.u64(0x5500+k),'slot '..k..' material replaced')
end
P.stop()
return 'ok'
""")

    def test_an_overlay_goes_with_its_virtual_identity_and_never_goes_stale(self):
        self.check(r"""
screen_1080({entries={{type=136},{type=22},{type=41},{type=130}},slot=0,rows={4,4,2},sections={0}})
for k=0,3 do place(k)end
local P=panel.panel({placeholders=5,focus=true,selection=true})
tick(4)
select_into(P,0)
select_into(P,2)
assert(slots_of(overlaid())=='V n V n')
-- I: the player picks a native stratagem into virtual slot 2 (the game writes the record and repaints): the slot is
-- plain again and its overlay goes at once.
W.write(SCREEN.record+LO.entries+2*LO.entryStride+LO.entryType,W.u32(22))
W.write(SCREEN.ui+LO.panel0BoundRecord,W.u64(0))
tick(2)
-- The overlay goes on the first frame the slot shows another type; the identity follows once the record has settled.
assert(SCREEN.widget(2)==22 and slots_of(overlaid())=='V n n n',table.concat(logged,' | '))
tick(4)
assert(slots_of(selector.virtual_slots().slots)=='V n n n')
assert(count('virtual slot 2 (orbital_gas_barrage) no longer holds its token: it now holds ')==1)
-- J: Gas Barrage into native slot 3: its overlay appears.
select_into(P,3)
assert(slots_of(overlaid())=='V n n V')
-- Undo (Ctrl+F7): slot 3 is restored and loses its overlay.
assert(P.cancel()=='restoring the slot')
assert(settle_job(P.handle).status=='restored')
tick(2)
assert(slots_of(overlaid())=='V n n n',table.concat(logged,' | '))
-- A slot that shows another type than its token for a moment (a repaint in flight) gets no overlay that frame.
W.write(widget(0)+LO.widgetType,W.u32(136))
tick(1)
assert(slots_of(overlaid())=='n n n n'and count('slot 0: no overlay: the slot shows type 136, not the token (type 118)')==1)
W.write(widget(0)+LO.widgetType,W.u32(118))
tick(1)
assert(slots_of(overlaid())=='V n n n')
-- K: the loadout screen closes: every overlay goes; reopened, it is drawn again on the slot that is still virtual.
SCREEN.close()
tick(2)
assert(next(overlaid())==nil and count('slot overlay overlays removed')>=1)
W.write(SCREEN.owner+LO.root,W.u64(SCREEN.ui))
tick(2)
assert(slots_of(overlaid())=='V n n n',table.concat(logged,' | '))
-- The native background not drawn: the plate takes the native grey (logged once).
W.write(widget(0)+O.background+O.primitive,W.u32(0xFFFFFFFF))
select_into(P,1)
local o=overlaid()
assert(o[0].plate.args[4][2]==36 and count('slot 0 (orbital_gas_barrage): the native icon background: the icon '
    ..'background is not drawn; the plate takes the native grey')==1,table.concat(logged,' | '))
-- In a mission nothing is drawn (the mission HUD's overlays are not activated).
mission({host=true})
tick(2)
assert(next(overlaid())==nil)
P.stop()
return 'ok'
""")

    def test_the_panel_can_still_be_drawn_in_main_world_and_without_slot_overlays(self):
        self.check(r"""
screen_1080({entries={{type=136}},slot=0,rows={4,4,2},sections={0}})
local P=panel.panel({placeholders=5,world='main',slot_overlays=false})
tick(4)
assert(P.shown and P.overlays==nil)
local g=guis()[1]
assert(calls[g].args[1]==MAIN,'the documented main_world fallback')
assert(P.status():find('GUI world main; slot overlays off',1,true),P.status())
P.stop()
local ok=pcall(panel.panel,{world='elsewhere'})
assert(not ok,'an unknown world is refused')
panel.WORLD='ui'
return 'ok'
""")



class VirtualIdentityTests(unittest.TestCase):
    """The Runtime's virtual identity survives everything the player does to other slots before a mission (the
    GasBarrageMissionProof 0.1.0 live run lost it): it follows only a settled record of the ship loadout before launch,
    and a drop says what the slot holds now."""

    def check(self, body):
        self.assertEqual(overlays(body), b'ok')

    def test_the_identity_survives_other_slots_the_selector_the_screen_and_the_launch(self):
        self.check(r"""
-- [GAS, then three stratagems picked natively] as in the live test: GAS into slot 0 of an empty loadout first.
screen_1080({entries={},slot=0,rows={4,4,2},sections={0}})
local P=panel.panel({placeholders=5,focus=true,selection=true})
tick(4)
select_into(P,0)
local function entry_at(k)return SCREEN.record+LO.entries+k*LO.entryStride end
local function repaint()W.write(SCREEN.ui+LO.panel0BoundRecord,W.u64(0))end
local function native_append(kind)
    local n=SCREEN.count()
    W.write(entry_at(n)+LO.entryType,W.u32(kind));W.write(entry_at(n)+LO.entryUses,W.u32(4294967295))
    W.write(SCREEN.record+LO.count,W.u32(n+1));repaint();tick(2)
end
local function virtual_text()return selector.slots_text(selector.virtual_slots())end
native_append(41);native_append(22);native_append(130)
tick(6)
assert(virtual_text()=='0 = orbital_gas_barrage',table.concat(logged,' | '))
assert(table.concat(selector.virtual_slots().pairs,',')==table.concat({PRECISION_ID,3193297673,2281932031,1298599997},','))
-- Another slot replaced natively in place.
W.write(entry_at(2)+LO.entryType,W.u32(130));repaint();tick(2)
W.write(entry_at(2)+LO.entryType,W.u32(22));repaint();tick(6)
assert(virtual_text()=='0 = orbital_gas_barrage')
-- The native selector opened and closed on every other slot.
for k=1,3 do
    SCREEN.set('selecting',false);tick(1);SCREEN.set('editedSlot',k);SCREEN.set('selecting',true);tick(3)
end
SCREEN.set('selecting',false);tick(6)
assert(virtual_text()=='0 = orbital_gas_barrage')
-- The loadout screen closes, then opens with its record not filled yet for a few frames (the game filling it).
SCREEN.close();tick(4)
local n=SCREEN.count()
W.write(SCREEN.record+LO.count,W.u32(0))
W.write(SCREEN.owner+LO.root,W.u64(SCREEN.ui));tick(2)
W.write(SCREEN.record+LO.count,W.u32(n));tick(8)
assert(virtual_text()=='0 = orbital_gas_barrage',table.concat(logged,' | '))
-- Readied and launched: the record the launch rewrites is not the player's edit.
SCREEN.set('ready',true);SCREEN.set('launched',true)
W.write(entry_at(0)+LO.entryType,W.u32(41));repaint();tick(8)
W.write(entry_at(0)+LO.entryType,W.u32(118));repaint()
SCREEN.set('ready',false);SCREEN.set('launched',false);tick(8)
assert(virtual_text()=='0 = orbital_gas_barrage',table.concat(logged,' | '))
-- In the mission the loadout screen's record is the game's: rewritten, then back aboard the ship.
mission({host=true})
W.write(SCREEN.record+LO.count,W.u32(0));repaint();tick(8)
W.write(SCREEN.record+LO.count,W.u32(n));W.state(3);repaint();tick(8)
assert(virtual_text()=='0 = orbital_gas_barrage'and count('no virtual slot remains')==0,table.concat(logged,' | '))
local slots,k=selector.reconstruct({PRECISION_ID,3193297673,2281932031,1298599997})
assert(k==1 and slots[0]=='orbital_gas_barrage')
-- Only the player replacing the virtual slot itself (here with the 120mm) makes it plain, and the log says with what.
W.write(entry_at(0)+LO.entryType,W.u32(136));repaint();tick(8)
assert(selector.virtual_slots()==nil and count('virtual slot 0 (orbital_gas_barrage) no longer holds its token: it now '
    ..'holds Orbital 120mm HE Barrage; that slot is plain again (the loadout order was Orbital Precision Strike; ')==1,
    table.concat(logged,' | '))
P.stop()
return 'ok'
""")

    def test_leaving_the_screen_right_after_a_native_pick_keeps_the_recorded_order_current(self):
        self.check(r"""
screen_1080({entries={},slot=0,rows={4,4,2},sections={0}})
local P=panel.panel({placeholders=5,focus=true,selection=true})
tick(4)
select_into(P,0)
local function entry_at(k)return SCREEN.record+LO.entries+k*LO.entryStride end
-- A native pick, then the player leaves at once (before the record has settled for half a second).
local n=SCREEN.count()
W.write(entry_at(n)+LO.entryType,W.u32(22));W.write(entry_at(n)+LO.entryUses,W.u32(4294967295))
W.write(SCREEN.record+LO.count,W.u32(n+1));W.write(SCREEN.ui+LO.panel0BoundRecord,W.u64(0))
tick(1)
SCREEN.close();tick(2)
local set=selector.virtual_slots()
assert(set and set.slots[0]and table.concat(set.pairs,',')==table.concat({PRECISION_ID,2281932031},','),
    table.concat(logged,' | '))
local slots,k=selector.reconstruct({PRECISION_ID,2281932031})
assert(k==1 and slots[0]=='orbital_gas_barrage')
P.stop()
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
