"""Runtime icon overlays over native stratagem slot icons (development; VISUAL ONLY; docs/custom-stratagems.md, "Slot
icon overlays"; runtime/stratagem_slot_overlay.lua; research slotOverlay, worldOrder): a screen GUI opened in the Ui World
(found by its position in the engine's world array), one bitmap of the Runtime image over each target slot's icon
element, at that element's own on-screen quad, following its moves and alpha and removed at once when the target goes.
The native slot (its type, its icon element, its material and its texture) is only read. Offline: the event world with a
loadout screen, the mission HUD's stratagem list, the Runtime image loaded and the recording stand-in engine GUI."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

RESEARCH = json.loads((ROOT / 'research/runtime-stratagem-ui-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

OVERLAY = r"""
local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local O,E=SEL.slotOverlay,SEL.grid.element
engine.Gui.update_bitmap=nothing('update_bitmap')
engine.Gui.material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return {kind='Material',gui=gui,material=m}end
engine.Material={set_vector4=function(...)calls[#calls+1]={name='set_vector4',args={...}}end}
engine.Quaternion={from_elements=function(x,y,z,w)return {kind='Quaternion',x,y,z,w}end}
local function of(name)local out={};for _,c in ipairs(calls)do if c.name==name then out[#out+1]=c end end;return out end
local function last(name)local l=of(name);return l[#l]end
-- The game context (the object the game state is read from) names the Ui World; the engine's world array lists the Game
-- World first and the Ui World second, as Application.worlds does (full userdata: matched by position).
local function u64_at(at)local s=W.read(at,8);local lo,hi=0,0
    for i=4,1,-1 do lo=lo*256+s:byte(i);hi=hi*256+s:byte(i+4)end;return lo+hi*4294967296 end
local context=u64_at(W.GAME+O.gameContext)
assert(context~=0)
local GAME_WORLD,UI_WORLD=0x24A96260080,0x24A97280080
W.write(context+O.uiWorld,W.u32(UI_WORLD%4294967296)..W.u32(math.floor(UI_WORLD/4294967296)))
W.engine_worlds({GAME_WORLD,UI_WORLD})
local UW=newproxy()
alive[2]=UW
-- An icon element's on-screen quad as the game lays it out: 64 x 64 units scaled to w x h at (x, y), alpha a.
local function place(element,x,y,w,h,a)
    W.write(element+E.size,W.f32(64)..W.f32(64))
    W.write(element+E.m00,W.f32(w/64));W.write(element+E.m02,W.f32(0))
    W.write(element+E.m20,W.f32(0));W.write(element+E.m22,W.f32(h/64))
    W.write(element+E.tx,W.f32(x));W.write(element+E.ty,W.f32(y))
    W.write(element+O.alpha,W.f32(a or 1))
end
local COLOURS={{'c0',0.8,1,0.431,0.357},{'c1',1,1,1,0.933},{'c2',0.2,0,0,0},{'c3',0,0,0,0}}
-- The ship loadout: four slots, their icons 64 px wide, 80 px apart.
local function ship()
    SCREEN=W.loadout_screen({entries={{type=136},{type=118},{type=22},{type=41}},selecting=false})
    SCREEN.frame()
    for k=0,3 do place(SCREEN.element(k),100+80*k,900,64,64)end
end
local VIRTUAL={}
local function ship_targets(world)
    local out={}
    for slot=0,3 do
        if VIRTUAL[slot]then
            local icon=overlay.ship_icon(world,slot)
            if icon then out[#out+1]={key=slot,icon=icon,label='slot '..slot}end
        end
    end
    return out
end
local function native_bytes()
    local out={}
    for k=0,3 do out[k]=W.read(SCREEN.element(k),0x160)..W.u32(SCREEN.widget(k))end
    return out
end
local function bitmaps_of(gui)local out={};for _,c in ipairs(of('bitmap'))do if c.args[1]==gui then out[#out+1]=c end end;return out end
local function at_xy(c,x,y,w,h,a)
    return c.args[3][1]==x and c.args[3][2]==y and c.args[3][3]==O.overlayLayer and c.args[4][1]==w and c.args[4][2]==h
        and c.args[5][1]==(a or 255)
end
"""


def lua(body):
    return run(WORLD + SELECT + OVERLAY + body)


class SlotOverlayResearchTests(unittest.TestCase):
    def test_the_render_order_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        exe = {pin['rva']: pin for pin in RESEARCH['pins']['exe']['worldOrder']}
        game = {pin['rva']: pin for pin in RESEARCH['pins']['game']['slotOverlay']}
        self.assertEqual(exe[0x3F823D]['asm'], 'mov ebp, dword ptr [rax + 0x590]')       # the engine's world count
        self.assertEqual(exe[0x3F826C]['asm'], 'mov rdx, qword ptr [rax + 0x598]')       # its world array
        self.assertEqual(exe[0x2693E3]['asm'], 'movss dword ptr [r14 + 0x70], xmm0')     # a batch depth from its layer
        self.assertEqual(game[0x1893095]['asm'], 'mov edx, 0xe')                         # the ship slot icon: layer 14
        self.assertEqual(game[0xAB7B18]['asm'], 'mov rcx, qword ptr [rbx + 0x1118]')     # the Ui World
        self.assertEqual(game[0x183599A]['asm'], 'mov dword ptr [rcx + 0x3748], r12d')   # the record entry shown
        self.assertTrue(RESEARCH['determinations']['slotOverlay'].startswith('A Runtime screen GUI created in the Ui World'))
        self.assertTrue(RESEARCH['determinations']['whereItAppears'].startswith('Application.main_world is the Game World'))

    def test_the_native_icon_background_research(self):
        game = {pin['rva']: pin for pin in RESEARCH['pins']['game']['slotBackground']}
        self.assertEqual(game[0x1892F2F]['asm'], 'mov dword ptr [rbp - 0x50], 0x3e109091')  # grey 36/255
        self.assertEqual(game[0x1892F4C]['asm'], 'mov edx, 0xc')                           # layer 12
        self.assertEqual(game[0x144E0D4]['asm'], 'jmp 0x1444030')                          # kind 5's push
        self.assertEqual(game[0x1444144]['asm'], 'mov r10, qword ptr [rcx + 0x108]')       # a filled rectangle
        layout = RESEARCH['layout']['slotOverlay']
        self.assertEqual((layout['background'], layout['backgroundLayer'], layout['backgroundGrey'],
            layout['effectiveColour'], layout['tint'], layout['tintLayer']), (0x110, 12, 36, 0x54, 0x228, 13))
        self.assertIn('The backing plate is the native icon background', RESEARCH['determinations']['slotOverlay'])

    def test_the_hud_chain_is_the_live_proven_calldown_list(self):
        self.assertEqual(lua(r"""
local H=require('hd2runtime/domains/stratagem_calldown').hud
assert(O.hudRoot==H.global and O.hudList+O.entries==H.pathOffset,'the same list')
assert(O.entryStride==H.slots.stride and O.entrySlot==H.slots.index and O.hudEntries==H.slots.count)
assert(O.primitive==SEL.slotIcon.primitive,'the image element primitive')
assert(O.overlayLayer>O.hudIconLayer and O.overlayLayer>O.shipIconLayer and O.overlayLayer<950
    and O.overlayLayer<=O.maxLayer,'above the slot icons, below the HUD 950-953 and the native 991-1018 parts')
return 'ok'
"""), b'ok')


class SlotOverlayTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_an_overlay_is_drawn_in_the_ui_world_over_the_native_icon_and_touches_nothing(self):
        self.check(r"""
ship()
local before=native_bytes()
local w=assert(world_module.open())
local uw,index=overlay.ui_world(w)
assert(uw==UW and index==2,'the Ui World by its position in the engine world list')
VIRTUAL[1]=true
local S=overlay.follow({image=ICON,colours=COLOURS,targets=ship_targets})
tick()
local g=of('create_screen_gui')
assert(#g==1 and g[1].args[1]==UW,'one screen GUI, in the Ui World (not main_world)')
local gui=#calls-#calls+1
for k,c in ipairs(calls)do if c.name=='create_screen_gui'then gui=k end end
local b=bitmaps_of(gui)
assert(#b==1 and b[1].args[2]==images.material_name(ICON),'the Runtime image, by its material')
assert(at_xy(b[1],180,900,64,64),'over slot 1 icon, at its quad and the overlay layer')
local sets=of('set_vector4')
assert(#sets==4 and sets[1].args[1].gui==gui and sets[1].args[2]=='c0'and sets[1].args[3][1]==0.8,
    'the icon shader colours on this GUI\'s own material instance')
assert(count('OVERLAY: 1 icon drawn over native slot icons (layer 940, the native icons untouched): slot 1 at 180, '
    ..'900, 64 x 64')==1,table.concat(logged,' | '))
assert(S.status()=='1 180,900 64x64 a1.00')
-- Nothing written: the native slot's type, icon element, material and texture are as they were.
assert(#W.runtime.writes==0,'nothing written')
local after=native_bytes()
for k=0,3 do assert(after[k]==before[k],'native slot '..k..' changed')end
S.stop()
assert(#of('destroy_gui')==1)
return 'ok'
""")

    def test_the_overlay_follows_the_native_icon_and_goes_at_once(self):
        self.check(r"""
ship()
VIRTUAL[2]=true
local S=overlay.follow({image=ICON,colours=COLOURS,targets=ship_targets})
tick()
assert(#of('create_screen_gui')==1 and#of('bitmap')==1 and at_xy(of('bitmap')[1],260,900,64,64))
-- Unchanged: nothing redrawn.
tick(3)
assert(#of('update_bitmap')==0 and#of('create_screen_gui')==1)
-- The native icon moves (a scroll or a layout change): the same bitmap moves with it.
W.write(SCREEN.element(2)+E.tx,W.f32(300))
tick()
local u=last('update_bitmap')
local id;for k,c in ipairs(calls)do if c.name=='bitmap'then id=k end end
assert(#of('update_bitmap')==1 and u.args[2]==id and u.args[3]==images.material_name(ICON),'the same bitmap, by its id')
assert(u.args[4][1]==300 and u.args[4][2]==900 and u.args[4][3]==O.overlayLayer and u.args[5][1]==64)
-- It fades: the overlay fades with it.
W.write(SCREEN.element(2)+O.alpha,W.f32(0.5))
tick()
assert(#of('update_bitmap')==2 and last('update_bitmap').args[6][1]==128)
assert(#of('create_screen_gui')==1,'moves are updates, never a new GUI')
-- The slot stops being virtual: the overlay is gone that very tick.
VIRTUAL[2]=nil
tick()
assert(#of('destroy_gui')==1 and count('slot overlay overlays removed')==1 and S.status()=='no overlay shown')
tick(3)
assert(#of('create_screen_gui')==1,'nothing drawn again')
assert(#W.runtime.writes==0)
S.stop()
return 'ok'
""")

    def test_each_slot_and_the_mixed_pattern(self):
        self.check(r"""
ship()
local before=native_bytes()
local S=overlay.follow({image=ICON,colours=COLOURS,targets=ship_targets})
local function gui_index()local k;for i,c in ipairs(calls)do if c.name=='create_screen_gui'then k=i end end;return k end
for slot=0,3 do
    VIRTUAL={[slot]=true}
    tick()
    local b=bitmaps_of(gui_index())
    assert(#b==1 and at_xy(b[1],100+80*slot,900,64,64),'slot '..slot)
    VIRTUAL={}
    tick()
    assert(#of('destroy_gui')==#of('create_screen_gui'),'slot '..slot..' removed')
end
-- virtual / native / virtual / native: two overlays, in one GUI, over slots 0 and 2 only.
VIRTUAL={[0]=true,[2]=true}
tick()
local b=bitmaps_of(gui_index())
assert(#b==2 and at_xy(b[1],100,900,64,64)and at_xy(b[2],260,900,64,64))
assert(count('OVERLAY: 2 icons drawn over native slot icons (layer 940, the native icons untouched): slot 0 at 100, '
    ..'900, 64 x 64; slot 2 at 260, 900, 64 x 64')==1)
assert(S.status()=='0 100,900 64x64 a1.00; 2 260,900 64x64 a1.00')
-- Slot 2 becomes native again: slot 0 keeps its overlay, slot 2 loses its own.
VIRTUAL[2]=nil
tick()
b=bitmaps_of(gui_index())
assert(#b==1 and at_xy(b[1],100,900,64,64)and#of('destroy_gui')==#of('create_screen_gui')-1)
VIRTUAL={}
tick()
assert(#of('destroy_gui')==#of('create_screen_gui'))
local after=native_bytes()
for k=0,3 do assert(after[k]==before[k])end
assert(#W.runtime.writes==0)
S.stop()
return 'ok'
""")

    def test_a_backing_plate_sits_under_the_overlay_and_follows_it(self):
        self.check(r"""
ship()
VIRTUAL={[3]=true}
local S=overlay.follow({image=ICON,colours=COLOURS,backing={255,20,22,24},targets=ship_targets})
tick()
local r=of('rect')
assert(#r==1 and r[1].args[2][1]==340 and r[1].args[2][2]==900 and r[1].args[2][3]==O.overlayLayer-1,
    'one plate, at the icon quad, one layer below the overlay')
assert(r[1].args[3][1]==64 and r[1].args[3][2]==64 and r[1].args[4][1]==255 and r[1].args[4][2]==20)
assert(#of('bitmap')==1 and at_xy(of('bitmap')[1],340,900,64,64))
assert(count('(layer 940, on a backing plate, the native icons untouched): slot 3 at 340, 900, 64 x 64')==1)
W.write(SCREEN.element(3)+O.alpha,W.f32(0.5))
tick()
local u=of('update_rect')
assert(#u==1 and u[1].args[5][1]==128 and#of('update_bitmap')==1,'the plate fades with the icon')
VIRTUAL={}
tick()
assert(#of('destroy_gui')==1 and#W.runtime.writes==0)
S.stop()
return 'ok'
""")

    def test_nothing_is_drawn_over_an_icon_that_is_not_shown_or_a_world_that_does_not_match(self):
        self.check(r"""
ship()
VIRTUAL={[1]=true}
local S=overlay.follow({image=ICON,colours=COLOURS,targets=ship_targets})
local function none(reason)
    tick()
    assert(#of('create_screen_gui')==0,reason..': drew')
    assert(count(reason)==1,reason..' | '..table.concat(logged,' | '))
end
local E1=SCREEN.element(1)
local primitive=W.read(E1+O.primitive,4)
W.write(E1+O.primitive,W.u32(0xFFFFFFFF))
none('slot overlay slot 1: no overlay: the native icon is not drawn')
W.write(E1+O.primitive,primitive)
W.write(E1+O.alpha,W.f32(0))
none('slot overlay slot 1: no overlay: the native icon is transparent')
W.write(E1+O.alpha,W.f32(1))
W.write(E1+E.m02,W.f32(0.5))
none('slot overlay slot 1: no overlay: the icon is rotated or unreadable')
W.write(E1+E.m02,W.f32(0))
-- The Ui World: Application.worlds must list exactly the engine's worlds, and the context's world must be among them.
alive[2]=nil
none('slot overlay not drawn: the Ui World: Application.worlds lists 1 worlds, the engine 2')
alive[2]=UW
W.engine_worlds({GAME_WORLD,0x1234560})
none('slot overlay not drawn: the Ui World: the world is not in the engine world list')
W.engine_worlds({GAME_WORLD,UI_WORLD})
-- The loadout screen closes: no target.
W.write(W.GAME+SEL.loadout.ownerGlobal,W.u64(0))
tick(2)
assert(#of('create_screen_gui')==0)
S.stop()
-- An image that is not loaded is never drawn.
W.write(W.GAME+SEL.loadout.ownerGlobal,W.u64(SCREEN.owner))
local missing=images.handle('not_loaded_icon',MOD)
S=overlay.follow({image=missing,targets=ship_targets})
none('slot overlay slot 1: not drawn: the overlay image is not loaded')
S.stop()
assert(#W.runtime.writes==0)
return 'ok'
""")

    def test_the_plate_colour_is_the_native_background_live_colour(self):
        self.check(r"""
ship()
local w=assert(world_module.open())
local bg=SCREEN.ui+SEL.loadout.panel0Widgets+SEL.loadout.widgetStride+O.background
W.write(bg+O.primitive,W.u32(7))
W.write(bg+O.effectiveColour,W.f32(1)..W.f32(36/255)..W.f32(0.5)..W.f32(1.5))
local c=assert(overlay.plate_colour(w,bg))
assert(c[1]==36 and c[2]==128 and c[3]==255,'(a, r, g, b) at +0x54, clamped')
W.write(bg+O.effectiveColour,W.f32(0))
assert(select(2,overlay.plate_colour(w,bg))=='the icon background is transparent')
W.write(bg+O.primitive,W.u32(0xFFFFFFFF))
assert(select(2,overlay.plate_colour(w,bg))=='the icon background is not drawn')
assert(overlay.PLATE[1]==36 and overlay.PLATE[2]==36 and overlay.PLATE[3]==36)
assert(#W.runtime.writes==0)
return 'ok'
""")

    def test_the_mission_target_is_ready_but_not_activated(self):
        self.check(r"""
mission({host=true})
local h=W.stratagem_hud({peer=LOCAL,slots={{type=136,code={}},{type=118,code={}}},record={{type=136},{type=118}}})
local w=assert(world_module.open())
local t=assert(overlay.mission_target(w,1,ICON,COLOURS))
assert(t.layer==O.hudOverlayLayer and t.icon==h.hud+O.hudList+O.entries+O.entryStride+O.widget+O.hudIcon
    and t.key=='mission 1'and t.plateElement==nil,'the HUD entry of loadout slot 1, at the HUD overlay layer')
assert(O.hudOverlayLayer>O.hudIconLayer and O.hudOverlayLayer<950)
return 'ok'
""")

    def test_another_build_draws_nothing(self):
        self.check(r"""
ship()
VIRTUAL={[0]=true}
local pin=SEL.pins[1]
local at=(pin.module=='exe'and W.EXE or W.GAME)+pin.rva
local saved=W.read(at,1)
W.write(at,string.char((saved:byte()+1)%256))
local S=overlay.follow({image=ICON,colours=COLOURS,targets=ship_targets})
tick(2)
assert(#of('create_screen_gui')==0 and count('slot overlay not drawn: loadout screen code changed')==1,
    table.concat(logged,' | '))
S.stop()
return 'ok'
""")

    def test_the_mission_hud_icon_of_each_loadout_slot(self):
        self.check(r"""
-- A record with a granted entry between the loadout entries: loadout slot 2 is record entry 3, HUD entry 3.
local RECORD={{type=136},{type=118},{type=130,granted=1},{type=22},{type=41}}
local function hud_slots()return {{type=136,code={}},{type=118,code={}},{type=130,code={}},{type=22,code={}},
    {type=41,code={}}}end
local w=assert(world_module.open())
local none,why=overlay.hud_entries(w)
assert(none==nil and why:find('the mission HUD is not shown',1,true))
mission({host=true})
local h=W.stratagem_hud({peer=LOCAL,slots=hud_slots(),record=RECORD})
w=assert(world_module.open())
local entries=assert(overlay.hud_entries(w))
local first=h.hud+O.hudList+O.entries
for k=0,4 do assert(entries[k].entry==first+k*O.entryStride and entries[k].icon==entries[k].entry+O.widget+O.hudIcon)end
local expected={[0]=0,1,3,4}
for slot=0,3 do
    local icon,hud=overlay.mission_icon(w,slot)
    assert(icon==first+expected[slot]*O.entryStride+O.widget+O.hudIcon,'slot '..slot..' -> HUD entry '..expected[slot])
    place(icon,40,500-60*slot,48,48)
end
assert(select(2,overlay.mission_icon(w,4))=='the loadout has no slot 4')
VIRTUAL={[0]=true,[2]=true}
local function mission_targets(world)
    local out={}
    for slot=0,3 do
        if VIRTUAL[slot]then
            local icon=overlay.mission_icon(world,slot)
            if icon then out[#out+1]={key=slot,icon=icon,label='mission slot '..slot}end
        end
    end
    return out
end
local before={}
for k=0,4 do before[k]=W.read(first+k*O.entryStride,O.entryStride)end
local S=overlay.follow({image=ICON,colours=COLOURS,targets=mission_targets})
tick()
local g=of('create_screen_gui')
assert(#g==1 and g[1].args[1]==UW,'the HUD is a Ui World GUI too')
local b=of('bitmap')
assert(#b==2 and at_xy(b[1],40,500,48,48)and at_xy(b[2],40,380,48,48),table.concat(logged,' | '))
-- A HUD entry showing another type than the record entry is never overlaid.
W.write(first+3*O.entryStride+require('hd2runtime/domains/stratagem_calldown').hud.slots.type,W.u32(41))
local icon,mismatch=overlay.mission_icon(w,2)
assert(icon==nil and mismatch=='the HUD entry shows type 41, the record entry is type 22')
W.write(first+3*O.entryStride+require('hd2runtime/domains/stratagem_calldown').hud.slots.type,W.u32(22))
-- The HUD not set up: nothing.
W.write(h.hud+require('hd2runtime/domains/stratagem_calldown').hud.setUp,string.char(0))
tick()
assert(#of('destroy_gui')==1 and count('slot overlay overlays removed')==1)
W.write(h.hud+require('hd2runtime/domains/stratagem_calldown').hud.setUp,string.char(1))
S.stop()
for k=0,4 do assert(W.read(first+k*O.entryStride,O.entryStride)==before[k],'HUD entry '..k..' changed')end
assert(#W.runtime.writes==0)
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
