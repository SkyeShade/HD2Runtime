"""The native-style CUSTOM STRATAGEMS panel (0.8.0, the user's UI overhaul; runtime/custom_stratagem_panel.lua
native_layout / draw_native / draw_native_focus, runtime/ui_fonts.lua; docs/custom-stratagems.md "The native-style
panel"). Offline, on the stand-in loadout screen of tests/test_custom_stratagem_panel.py (1080p, 1 px per unit; the
native list frame 75, 104, 395 x 528; the details panel 500, 232, 1024 x 400):
  * four columns of native-sized cards (80 at the 85 pitch) right of the details panel, in the native list's band, up
    to six rows; seven entries in two rows, no scrollbar (live r25: the 3-column, 2-row panel hid the seventh);
  * thirty entries: six of eight rows in view, a scrollbar; the wheel over the panel and the scrollbar track scroll it,
    the keyboard focus scrolls to its card; nothing is ever written;
  * every card in the native look: the translucent inner square, the six bars of the split frame, the icon on its
    plate; the equipped look (yellow frame) for a custom stratagem in a loadout slot; the white split frame when focused;
  * the title in FS Sinclair Medium when the Runtime's fonts are loaded, else monaco (logged);
  * the focused card's details drawn over the native details panel: a plate over its interior above the native layers
    (800-803), the category, name, description, STATS and ITEM TRAITS boxes and rows."""
import unittest

from test_custom_stratagem_panel import lua


NATIVE = r"""
local fonts=require('hd2runtime/runtime/ui_fonts');fonts.reset_for_tests()
local UF=require('hd2runtime/domains/ui_fonts')
local WHEEL=0
engine.Mouse={axis_index=function(name)return name end,button_index=function(name)return name end,
    axis=function(i)if i=='wheel'then return {x=0,y=WHEEL,z=0}end;return {x=0,y=0,z=0}end,button=function()return 0 end}
local input=require('hd2runtime/runtime/input')
local MOUSE={x=10,y=10,w=1920,h=1080,left=false,focused=true}
input.set_backend({focused=function()return MOUSE.focused end,down=function(code)return code==input.LBUTTON and MOUSE.left end,
    mouse=function()return MOUSE.x,MOUSE.y,MOUSE.w,MOUSE.h end})
local function point_at(r)MOUSE.x,MOUSE.y=r.x+r.w/2,1080-(r.y+r.h/2)end
local function texts_in(g)local out={};for _,c in ipairs(gui_calls(g,'text'))do out[#out+1]=c.args[2]end;return out end
local function has(list,text)for _,t in ipairs(list)do if t==text then return true end end;return false end
local DETAILS={category='CUSTOM SUPPLY STRATAGEM',name='Orbital Gas Barrage',description='A barrage of gas shells over '
    ..'the beacon, for ten seconds, burning everything that breathes in the area. It needs no ammunition.',
    stats={{'CALL-IN TIME','5.25 SEC'},{'USES','UNLIMITED'},{'COOLDOWN TIME','60 SEC'},
        {'CALL-IN CODE','UP UP DOWN DOWN',code={'up','up','down','down'}}},
    traits={'CUSTOM STRATAGEM','ORBITAL'}}
"""


class NativePanelTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(NATIVE + body), b'ok')

    def test_seven_entries_in_four_columns_and_no_scrollbar(self):
        self.check(r"""
local D1=screen_1080()
local P=panel.panel({renderer='native',placeholders=6,focus=true})
tick(4)
assert(P.shown and P.renderer=='native',table.concat(logged,' | '))
local L=P.layout
assert(L.grid.columns==4 and L.grid.rows==2 and L.grid.totalRows==2 and L.scrollbar==nil,L.grid.rows)
for k=1,7 do assert(L.tiles[k].visible,'every entry is in view: '..k)end
assert(near(L.tile,80)and near(L.pitch,85),'native-sized cards at the native pitch')
assert(not meets(L.panel,D1)and not meets(L.panel,{x=75,y=104,w=395,h=528}),'clear of the native details and list')
assert(L.panel.x>=D1.x+D1.w and L.panel.x+L.panel.w<=1920,'right of the details panel, inside the screen')
-- the title: monaco here (the Runtime fonts are not loaded in this world), logged as such
assert(count('title font core/performance_hud/monaco (FS Sinclair not loaded: monaco)')==1,table.concat(logged,' | '))
local g=guis()[1]
assert(has(texts_in(g),'CUSTOM STRATAGEMS'))
-- each visible card: the inner square and the six bars of its split frame
local frames=0
for _,c in ipairs(gui_calls(g,'rect'))do if c.args[2][3]==panel.LAYER_BASE+13 then frames=frames+1 end end
assert(frames==7*6,'six frame bars a card: '..frames)
assert(#W.runtime.writes==0)
P.stop()
return 'ok'
""")

    def test_thirty_entries_scroll_with_the_wheel_the_scrollbar_and_the_focus(self):
        self.check(r"""
screen_1080()
local P=panel.panel({renderer='native',placeholders=29,focus=true,mouse=true})
tick(4)
local L=P.layout
assert(L.grid.rows==6 and L.grid.totalRows==8 and L.scrollbar~=nil,tostring(L.grid.rows))
assert(L.tiles[24].visible and not L.tiles[25].visible)
assert(count('6 of 8 rows in view, scrolled to row 0 (wheel or scrollbar)')==1,table.concat(logged,' | '))
-- the wheel over the panel scrolls down one row (wheel -1), back up (+1)
point_at(L.tiles[6].rect)
tick(1)
WHEEL=-1;tick(1);WHEEL=0;tick(1)
assert(P.layout.grid.scroll==1 and P.layout.tiles[25].visible and not P.layout.tiles[4].visible,P.layout.grid.scroll)
WHEEL=1;tick(1);WHEEL=0;tick(1)
assert(P.layout.grid.scroll==0)
-- outside the panel the wheel is not the panel's
MOUSE.x,MOUSE.y=10,10
WHEEL=-1;tick(1);WHEEL=0;tick(1)
assert(P.layout.grid.scroll==0)
-- a click on the scrollbar track below the thumb: a page down (the last rows)
local t=P.layout.scrollbar.track
MOUSE.x,MOUSE.y=t.x+t.w/2,1080-(t.y+2)
MOUSE.left=true;tick(1);MOUSE.left=false;tick(1)
assert(P.layout.grid.scroll==2 and P.layout.tiles[30].visible,P.layout.grid.scroll)
-- the keyboard focus on a card out of view scrolls to it
MOUSE.x,MOUSE.y=10,10;tick(1)
for _=1,3 do P.focus_next()end
assert(P.focus==3 and P.layout.tiles[3].visible and P.layout.grid.scroll==0,tostring(P.layout.grid.scroll))
assert(#W.runtime.writes==0)
P.stop()
return 'ok'
""")

    def test_the_card_looks_the_fonts_and_the_details_overlay(self):
        self.check(r"""
local D1=screen_1080()
-- the Runtime's FS Sinclair fonts loaded (the resource table answers for their names)
local real=images.loaded
images.loaded=function(runtime,kind,name)
    if name==UF.fonts.title.name or name==UF.fonts.body.name then return true end
    return real(runtime,kind,name)
end
-- one custom stratagem in a loadout slot: the equipped look
selector.set_virtual_slots_for_tests({slots={[2]={definition='orbital_gas_barrage',token=PRECISION_ID,type=118}},
    pairs={136,22,PRECISION_ID}})
local P=panel.panel({renderer='native',placeholders=2,focus=true,mouse=true,details=function(id)return DETAILS end})
tick(4)
assert(P.shown and count('(FS Sinclair)')==1,table.concat(logged,' | '))
local g=guis()[1]
local title
for _,c in ipairs(gui_calls(g,'text'))do if c.args[2]=='CUSTOM STRATAGEMS'then title=c end end
assert(title and title.args[3]==UF.fonts.title.name and title.args[5]==UF.fonts.title.name,'FS Sinclair Medium')
-- the title's cap height is the native list header's: 13 units
assert(near(title.args[4]*UF.fonts.title.cap/UF.fonts.title.em,13),'cap height '..title.args[4])
local yellow=0
for _,c in ipairs(gui_calls(g,'rect'))do
    local col=c.args[4]
    if c.args[2][3]==panel.LAYER_BASE+13 and col and col[2]==132 and col[3]==121 and col[4]==8 then yellow=yellow+1 end
end
assert(yellow==6,'the equipped card has the native yellow frame: '..yellow)
-- hover the custom card: the white split frame and its details over the native details panel
point_at(P.layout.tiles[1].rect)
tick(1)
assert(P.focus==1 and count('its details drawn over the native details panel 500, 232, 1024 x 400')==1,
    table.concat(logged,' | '))
local f=guis()[#guis()]
local plate
for _,c in ipairs(gui_calls(f,'rect'))do if c.args[2][3]==panel.LAYER_BASE+20 then plate=rect_of(c)end end
assert(plate and inside(plate,D1)and plate.w>=1000 and plate.h>=380,'the plate covers the native details interior')
assert(panel.LAYER_BASE+20>803 and panel.LAYER_BASE+24<991,'above the native details layers, below the native popups')
local t=texts_in(f)
-- the call-in code in the game's arrows (U+2191 UP, U+2193 DOWN: glyphs of the Runtime's FS Sinclair), not in words
local ARROWS=panel.ARROWS.up..' '..panel.ARROWS.up..' '..panel.ARROWS.down..' '..panel.ARROWS.down
assert(ARROWS=='\226\134\145 \226\134\145 \226\134\147 \226\134\147'and fonts.has(UF.fonts.title,ARROWS))
for _,want in ipairs({'CUSTOM SUPPLY STRATAGEM','ORBITAL GAS BARRAGE','STATS','ITEM TRAITS','CALL-IN TIME','5.25 SEC',
    'USES','UNLIMITED','COOLDOWN TIME','60 SEC','CALL-IN CODE',ARROWS,'CUSTOM STRATAGEM','ORBITAL'})do
    assert(has(t,want),'drawn: '..want..' (have '..table.concat(t,' | ')..')')
end
assert(not has(t,'UP UP DOWN DOWN'),'the words are not drawn with the arrows')
-- the layout: the four stats in order, top to bottom, in the STATS box; each box title inside its box, under the top
-- edge, the top edge starting right of the title
local function text_call(s)for _,c in ipairs(gui_calls(f,'text'))do if c.args[2]==s then return c end end end
local y={}
for k,label in ipairs({'CALL-IN TIME','USES','COOLDOWN TIME','CALL-IN CODE'})do y[k]=text_call(label).args[6][2]end
assert(y[1]>y[2]and y[2]>y[3]and y[3]>y[4],'top to bottom: '..table.concat(y,', '))
local D=panel.DETAILS
local top=D1.y+D1.h-D.stats.box[2]*D1.h/400
local bottom=D1.y+D1.h-D.stats.box[4]*D1.h/400
assert(y[1]<top and y[4]>bottom,'inside the STATS box')
for _,title in ipairs({'STATS','ITEM TRAITS'})do
    local c=text_call(title)
    local cap=c.args[4]*UF.fonts.title.cap/UF.fonts.title.em
    assert(c.args[6][2]+cap<top and c.args[6][2]+cap>top-3*D1.h/400,title..' hangs under the top edge')
end
-- the arrows' row: the code value right-aligned at the value column, as the other values
local code=text_call(ARROWS)
local value=text_call('60 SEC')
local right=function(c)return c.args[6][1]+fonts.width(UF.fonts.title,c.args[2],c.args[4])end
assert(near(right(code),right(value)),'right-aligned: '..right(code)..' '..right(value))
-- the description wrapped to the panel's width in FS Sinclair (the body font)
local desc={}
for _,c in ipairs(gui_calls(f,'text'))do if c.args[3]==UF.fonts.body.name then desc[#desc+1]=c.args[2]end end
assert(#desc>=1 and #desc<=4 and table.concat(desc,' '):find('^A barrage of gas shells'),table.concat(desc,' / '))
local white=0
for _,c in ipairs(gui_calls(f,'rect'))do
    local col=c.args[4]
    if c.args[2][3]==panel.LAYER_BASE+18 and col and col[2]==255 and col[3]==255 then white=white+1 end
end
assert(white==6,'the focused card has the white split frame')
-- leaving the card removes the overlay: the native details panel shows again
MOUSE.x,MOUSE.y=10,10
tick(1)
assert(P.focus==nil and called('destroy_gui')>=1)
-- without the Runtime's fonts (monaco, which has no arrows) the code is drawn in words
images.loaded=real
fonts.reset_for_tests()
point_at(P.layout.tiles[1].rect)
tick(1)
local m=texts_in(guis()[#guis()])
assert(has(m,'UP UP DOWN DOWN')and not has(m,ARROWS),table.concat(m,' | '))
assert(#W.runtime.writes==0)
P.stop()
return 'ok'
""")

    def test_the_equipped_look_follows_the_picks(self):
        # Live r27: the panel opened while the selector still held the last mission's four picks, the selector dropped
        # them a moment later, and the cards stayed yellow while the new picks never lit up.
        self.check(r"""
screen_1080()
local function panel_gui()
    local found
    for _,g in ipairs(guis())do
        for _,c in ipairs(gui_calls(g,'text'))do if c.args[2]=='CUSTOM STRATAGEMS'then found=g end end
    end
    return found
end
local function yellow_cards()
    local n=0
    for _,c in ipairs(gui_calls(panel_gui(),'rect'))do
        local col=c.args[4]
        if c.args[2][3]==panel.LAYER_BASE+13 and col and col[2]==132 and col[3]==121 and col[4]==8 then n=n+1 end
    end
    return n/6                                  -- six bars a split frame
end
local last={slots={[2]={definition='orbital_gas_barrage',token=PRECISION_ID,type=118}},pairs={136,22,PRECISION_ID}}
selector.set_virtual_slots_for_tests(last)
local P=panel.panel({renderer='native',placeholders=2,focus=true,mouse=true,details=function(id)return DETAILS end})
tick(4)
assert(P.shown and yellow_cards()==1,'opened with the last picks: '..yellow_cards())
-- The selector drops them (the saved loadout no longer holds their tokens): the cards follow.
selector.set_virtual_slots_for_tests(nil)
tick(1)
assert(yellow_cards()==0 and count('the loadout picks changed')==1,table.concat(logged,' | '))
-- A pick lights its card at once (no wait for the next visit).
local before=called('destroy_gui')
selector.set_virtual_slots_for_tests(last)
tick(1)
assert(yellow_cards()==1 and called('destroy_gui')>before,'redrawn with the pick: '..yellow_cards())
-- Nothing changed: no redraw.
local n=called('destroy_gui')
tick(3)
assert(called('destroy_gui')==n,'redrawn only on a change: '..table.concat(logged,' | '))
assert(#W.runtime.writes==0)
P.stop()
return 'ok'
""")

    def test_five_traits_fit_the_traits_box(self):
        # CUSTOM STRATAGEM and four of the definition's (spec.traits; EAT-23: SUPPORT WEAPON, ANTI-TANK, STUN, EXPENDABLE):
        # five rows at a tighter pitch, every one inside the ITEM TRAITS box.
        self.check(r"""
local D1=screen_1080()
local five={}
for k,v in pairs(DETAILS)do five[k]=v end
five.traits={'CUSTOM STRATAGEM','SUPPORT WEAPON','ANTI-TANK','STUN','EXPENDABLE'}
local P=panel.panel({renderer='native',placeholders=2,focus=true,mouse=true,details=function(id)return five end})
tick(4)
point_at(P.layout.tiles[1].rect)
tick(1)
local f=guis()[#guis()]
local D=panel.DETAILS
local top=D1.y+D1.h-D.traits.box[2]*D1.h/400
local bottom=D1.y+D1.h-D.traits.box[4]*D1.h/400
local ys={}
for _,c in ipairs(gui_calls(f,'text'))do
    for k,t in ipairs(five.traits)do if c.args[2]==t and c.args[6][1]>D1.x+D1.w/2 then ys[k]=c.args[6][2]end end
end
for k=1,5 do assert(ys[k],'trait '..k..' drawn')end
for k=1,4 do assert(ys[k]>ys[k+1],'top to bottom')end
local cap=15*D1.h/400
assert(ys[1]+cap<top and ys[5]>bottom,'inside the box: '..ys[1]..' '..ys[5])
P.stop()
return 'ok'
""")

    def test_text_width_and_wrapping(self):
        self.check(r"""
local f=UF.fonts.body
assert(fonts.width(f,'',20)==0)
local w1,w2=fonts.width(f,'i',20),fonts.width(f,'W',20)
assert(w1>0 and w2>w1,'proportional')
local lines=fonts.wrap(f,'one two three four five six seven eight nine ten eleven twelve',20,120,3)
assert(#lines==3 and lines[3]:find('%.%.%.$'),table.concat(lines,' / '))
for _,l in ipairs(lines)do assert(fonts.width(f,l,20)<=120+1e-6,l)end
local n=0;for _,cp in fonts.utf8_codes('A\195\169\226\128\148')do n=n+1;assert(cp==65 or cp==233 or cp==0x2014)end
assert(n==3)
assert(fonts.font({},'title').fallback,'not loaded in an empty world: monaco')
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
