"""The game's own HUD icons in mod overlays (hd2.resources.game_icon; runtime/game_icons.lua, docs/game-icons.md):
the generated name table, the handles, the atlas sprite record read from the game's resource-manager layout, and the
overlay drawing them through d:image against a recording fake of the engine GUI API: Gui.bitmap_uv with the sprite's
rectangle, this GUI's material instance given the colours and the atlas page (Material.set_texture 'diffuse_map'), a
carrier material for boosters and second colour sets, and the GUI closed when a page in use unloads. Offline: nothing
here touches a game process, and set_texture never names a page the hooks do not report loaded."""
import subprocess
import sys
import unittest

from support import ROOT, run
from test_ui_overlay import HARNESS
from test_custom_images import family


class GameIconTableTests(unittest.TestCase):
    def test_the_generated_table_is_current_and_names_every_icon(self):
        status = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/generate_game_icons.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertEqual(run(r'''
local D=require('hd2runtime/domains/hud_icons')
local n,m=0,0
for name,sprite in pairs(D.stratagems)do n=n+1;assert(#sprite==16 and sprite:match('^%x+$'),name)end
for name,sprite in pairs(D.boosters)do m=m+1;assert(#sprite==16 and sprite:match('^%x+$'),name)end
assert(n==94 and m==20,n..' '..m)
assert(D.stratagems['EXO-45 Patriot Exosuit']=='396ECA60A6E80E17')
assert(D.boosters['Vitality Enhancement']=='A9C52A2333DFCB68')
assert(D.missing['SG-88 Break-Action Shotgun'])
return 'ok'
'''), b'ok')

    def test_handles(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local G=require('hd2runtime/runtime/game_icons')
local a=assert(hd2.resources.game_icon('stratagem','EXO-45 Patriot Exosuit'))
assert(hd2.resources.game_icon('stratagem','EXO-45 Patriot Exosuit')==a,'one handle per icon')
assert(G.issued(a)and G.identity(a).sprite=='396ECA60A6E80E17'and tostring(a)=='game icon stratagem: EXO-45 Patriot Exosuit')
assert(G.issued(hd2.resources.game_icon('booster','Vitality Enhancement')))
local h,code,why=hd2.resources.game_icon('weapon','AR-23 Liberator')
assert(h==nil and code=='UNKNOWN_KIND')
h,code,why=hd2.resources.game_icon('stratagem','Nope')
assert(h==nil and code=='UNKNOWN_ICON'and why:find('game_icons',1,true))
h,code,why=hd2.resources.game_icon('stratagem','SG-88 Break-Action Shotgun')
assert(h==nil and code=='UNKNOWN_ICON'and why:find('no HUD icon',1,true),why)
local names=hd2.resources.game_icons('booster')
assert(#names==20 and names[1]<names[2])
assert(#G.carriers()==94)
return 'ok'
'''), b'ok')


class AtlasSpriteTests(unittest.TestCase):
    """runtime/image_resources.lua atlas_sprite on the game's resource-manager layout: the sprite map entry's record,
    read as the image setter reads it (+8 the page, +0x10 the size, +0x18 the rectangle), validated."""

    def check(self, body):
        self.assertEqual(family(body), b'ok')

    def test_the_record_resolves_and_is_validated(self):
        self.check(r'''
local V,PAGE='content/ui/stratagem_icon_test','content/ui/atlas_page_test'
local vh,vl=images.hash(V)
local ph,pl=images.hash(PAGE)
W.icon_resources({textures={PAGE},materials={V},
    sprites={{name=V,atlas=PAGE,size={256,256},rect={0.8046875,0.23828125,0.0625,0.0625}}}})
local s=assert(images.atlas_sprite(W.runtime,vh,vl))
assert(s.page==string.format('%08X%08X',ph,pl)and s.w==256 and s.h==256 and s.page_w==4096 and s.page_h==4096)
assert(s.u==0.8046875 and s.v==0.23828125 and s.du==0.0625 and s.dv==0.0625)
assert(images.texture_loaded(W.runtime,ph,pl)==true and images.icon_material(W.runtime,vh,vl)==true)
-- not loaded, off its page, not a whole-pixel rectangle
local s2,why=images.atlas_sprite(W.runtime,images.hash('content/ui/other'))
assert(s2==nil and why:find('not loaded',1,true),why)
W.icon_resources({sprites={{name=V,atlas=PAGE,size={256,256},rect={0.95,0.2,0.0625,0.0625}}}})
s2,why=images.atlas_sprite(W.runtime,vh,vl)
assert(s2==nil and why:find('off its page',1,true),why)
W.icon_resources({sprites={{name=V,atlas=PAGE,size={256,256},rect={0.5,0.2,0.07,0.0625}}}})
s2,why=images.atlas_sprite(W.runtime,vh,vl)
assert(s2==nil and why:find('whole-pixel',1,true),why)
-- the resolver: a stratagem icon needs its sprite, its page and its own icon material
local G=require('hd2runtime/runtime/game_icons')
W.icon_resources({textures={PAGE},materials={V},
    sprites={{name=V,atlas=PAGE,size={256,256},rect={0.5,0.25,0.0625,0.0625}}}})
local D=require('hd2runtime/domains/hud_icons')
D.stratagems['Test Icon']=string.format('%08X%08X',vh,vl)
local icon=assert(G.handle('stratagem','Test Icon'))
local spec=assert(G.resolve(W.runtime,icon))
assert(spec.own==spec.sprite and spec.page==string.format('%08X%08X',ph,pl))
assert(spec.rect[1]==0.5 and spec.rect[3]==0.0625 and spec.page_w==4096 and spec.w==256)
-- the UVs for a box: half a page pixel at full size; one texel of the sampled mip level when drawn smaller
local full=G.uv(spec,256,256)
assert(math.abs(full[1]-(0.5+0.5/4096))<1e-12 and math.abs(full[4]-(0.3125-0.5/4096))<1e-12,'half a pixel at full size')
local quarter=G.uv(spec,64,64)
assert(math.abs(quarter[1]-(0.5+4/4096))<1e-12 and math.abs(quarter[3]-(0.5625-4/4096))<1e-12,'mip 2: 4 page pixels')
local small=G.uv(spec,90,90)
assert(math.abs(small[1]-(0.5+4/4096))<1e-12,'256 / 90 samples mip 2 too')
local tiny=G.uv(spec,4,4)
assert(math.abs(tiny[1]-(0.5+16/4096))<1e-12,'at most 16 page pixels')
W.icon_resources({materials={V},sprites={{name=V,atlas=PAGE,size={256,256},rect={0.5,0.25,0.0625,0.0625}}}})
local none,nwhy=G.resolve(W.runtime,icon)
assert(none==nil and nwhy:find('atlas page is not loaded',1,true),nwhy)
assert(writes()==0)
return 'ok'
''')


ICONS = r'''
stingray.Gui.bitmap_uv=rec('bitmap_uv',newid)
stingray.Gui.update_bitmap_uv=rec('update_bitmap_uv')
stingray.Gui.material=rec('material',function(gui,m)return {material=m}end)
stingray.Material={set_vector4=rec('set_vector4'),set_texture=rec('set_texture')}
stingray.Quaternion={from_elements=function(...)temp=temp+16;return{...}end}
stingray.IdString64={from_hex=function(h)temp=temp+16;return {id=h}end}
local G=require('hd2runtime/runtime/game_icons')
local PAGES={["5207684C3952B0CC"]=true,["6E09D5A15DEC6F79"]=true,["18EDBED388A3D706"]=true}
local MATERIALS={}
for _,m in ipairs(G.carriers())do MATERIALS[m]=true end
local SPECS={}
O.hooks.game_icon=function(world,h)
    local s=SPECS[G.identity(h).name]
    if not s then return nil,'not loaded'end
    if not PAGES[s.page]then return nil,'its atlas page is not loaded'end
    return s
end
O.hooks.page_loaded=function(world,page)return PAGES[page]==true end
O.hooks.material_loaded=function(world,m)return MATERIALS[m]==true end
local patriot=hd2.resources.game_icon('stratagem','EXO-45 Patriot Exosuit')
local c4=hd2.resources.game_icon('stratagem','B/MD C4 Pack')
local vitality=hd2.resources.game_icon('booster','Vitality Enhancement')
SPECS['EXO-45 Patriot Exosuit']={sprite='396ECA60A6E80E17',own='396ECA60A6E80E17',page='5207684C3952B0CC',uv={0.1,0.2,0.3,0.4}}
SPECS['B/MD C4 Pack']={sprite='286AD42DBC7314D0',own='286AD42DBC7314D0',page='6E09D5A15DEC6F79',uv={0.5,0.5,0.6,0.6}}
SPECS['Vitality Enhancement']={sprite='A9C52A2333DFCB68',page='18EDBED388A3D706',uv={0.7,0.1,0.75,0.2}}
local function textures()
    local out={}
    for _,c in ipairs(calls)do if c.name=='set_texture'then out[#out+1]={c.args[1].material.id,c.args[2],c.args[3].id}end end
    return out
end
'''


class OverlayGameIconTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + ICONS + body), b'ok')

    def test_a_stratagem_icon_draws_its_sprite_through_its_own_material(self):
        self.lua(r'''
local x=100
local ov=hd2.ui.overlay({owner='mods/t/arcade'})
ov:draw(function(d)d:image(patriot,x,50,64,64,{colours={r='#FF6E5C'}})end)
frames(1)
assert(called('bitmap_uv')==1 and called('bitmap')==0)
local b=last('bitmap_uv').args
assert(b[2].id=='396ECA60A6E80E17','the stratagem own icon material')
assert(b[3][1]==0.1 and b[3][2]==0.2 and b[4][1]==0.3 and b[4][2]==0.4,'uv00 the top-left, uv11 the bottom-right')
assert(b[5][1]==100 and b[5][2]==1080-50-64 and b[6][1]==64)
local t=textures()
assert(#t==1 and t[1][1]=='396ECA60A6E80E17'and t[1][2]=='diffuse_map'and t[1][3]=='5207684C3952B0CC','the page on this instance')
assert(called('set_vector4')==4)
local n=#calls;frames(5)
assert(#calls==n,'an unchanged frame calls nothing')
x=200;frames(1)
assert(called('update_bitmap_uv')==1 and called('bitmap_uv')==1 and #textures()==1,'a move updates the bitmap only')
return 'ok'
''')

    def test_boosters_and_second_colour_sets_borrow_a_carrier(self):
        self.lua(r'''
local ov=hd2.ui.overlay({owner='mods/t/arcade'})
ov:draw(function(d)
    d:image(patriot,10,10,64,64,{colours={r='#FF0000'}})
    d:image(patriot,90,10,64,64,{colours={r='#00FF00'}})     -- a second colour set of one stratagem
    d:image(vitality,170,10,64,64)                           -- a booster: no material of its own
    d:image(vitality,250,10,64,64)                           -- the same booster again: the same carrier
end)
frames(1)
assert(called('bitmap_uv')==4 and ov:status().refused==0,tostring(ov:status().first_refusal))
local mats={}
for _,c in ipairs(calls)do if c.name=='bitmap_uv'then mats[#mats+1]=c.args[2].id end end
assert(mats[1]=='396ECA60A6E80E17','the first colour set keeps the own material')
assert(mats[2]~=mats[1]and mats[3]~=mats[1]and mats[3]~=mats[2],'carriers are other icon materials')
assert(mats[4]==mats[3],'one carrier per (page, colours)')
local seen={}
for _,t in ipairs(textures())do
    assert(seen[t[1]]==nil or seen[t[1]]==t[3],'one page per material')
    seen[t[1]]=t[3]
end
assert(seen[mats[3]]=='18EDBED388A3D706'and seen[mats[1]]=='5207684C3952B0CC'and seen[mats[2]]=='5207684C3952B0CC')
-- stable: the same frame again changes nothing
local n=#calls;frames(3)
assert(#calls==n)
-- a carrier needed by its own stratagem: the stratagem takes its material back, the booster moves to another carrier
local first=G.carriers()[1]
local owner
for name,sprite in pairs(require('hd2runtime/domains/hud_icons').stratagems)do if sprite==first then owner=name end end
SPECS[owner]={sprite=first,own=first,page='5207684C3952B0CC',uv={0.2,0.2,0.3,0.3}}
local owner_icon=hd2.resources.game_icon('stratagem',owner)
ov:draw(function(d)d:image(vitality,170,10,64,64)end)
frames(1)
assert(last('bitmap_uv')and(function()for i=#calls,1,-1 do local c=calls[i]
    if c.name=='bitmap_uv'or c.name=='update_bitmap_uv'then return true end end end)())
local booster_carrier
ov:draw(function(d)d:image(owner_icon,10,10,64,64);d:image(vitality,170,10,64,64)end)
frames(1)
local drawn=ov:status().items
assert(drawn==2,'both drawn: '..tostring(ov:status().first_refusal))
local last_page={}
for _,t in ipairs(textures())do last_page[t[1]]=t[3]end
assert(last_page[first]=='5207684C3952B0CC','the stratagem got its own material back, on its own page')
for m,page in pairs(last_page)do if page=='18EDBED388A3D706'and m~=first then booster_carrier=m end end
assert(booster_carrier,'the booster drawn through another carrier on the booster page')
return 'ok'
''')

    def test_an_unloaded_page_is_never_named_and_closes_the_gui(self):
        self.lua(r'''
local ov=hd2.ui.overlay({owner='mods/t/arcade'})
ov:draw(function(d)d:image(patriot,10,10,64,64);d:image(vitality,90,10,64,64)end)
PAGES["18EDBED388A3D706"]=false
frames(1)
assert(called('bitmap_uv')==1 and ov:status().waiting_images==1,'the booster waits for its page')
for _,t in ipairs(textures())do assert(t[3]~='18EDBED388A3D706','an unloaded page never reaches set_texture')end
PAGES["18EDBED388A3D706"]=true
frames(61)
assert(called('bitmap_uv')==2,'drawn once its page is loaded')
local guis=called('create_screen_gui')
-- the booster atlas unloads (a mission starts): the GUI with its instances is closed first, then drawn without it
PAGES["18EDBED388A3D706"]=false
frames(1)
assert(called('destroy_gui')>=1 and called('create_screen_gui')==guis+1,'closed and reopened')
local before=#textures()
frames(2)
for i=before+1,#textures()do assert(textures()[i][3]~='18EDBED388A3D706')end
assert(ov:status().waiting_images==1)
return 'ok'
''')

    def test_without_update_bitmap_uv_a_moved_icon_is_replaced(self):
        self.lua(r'''
stingray.Gui.update_bitmap_uv=nil
local x=10
local ov=hd2.ui.overlay({owner='mods/t/arcade'})
ov:draw(function(d)d:image(patriot,x,10,64,64)end)
frames(1)
x=20;frames(1)
assert(called('bitmap_uv')==2 and called('destroy_bitmap')==1)
return 'ok'
''')

    def test_engine_gui_bitmap_uv_and_set_texture_argument_order(self):
        self.lua(r'''
local engine_gui=require('hd2runtime/runtime/engine_gui')
local screen=assert(engine_gui.open({world='UI',max_layer=1023}))
local id=assert(screen.bitmap_uv('396ECA60A6E80E17',{0.1,0.2,0.3,0.4},5,6,7,8,9,{255,1,2,3}))
local b=last('bitmap_uv').args
assert(b[1]:match('^GUI')and b[2].id=='396ECA60A6E80E17'and b[3][1]==0.1 and b[4][2]==0.4 and b[5][3]==7 and b[6][2]==9)
assert(screen.update_bitmap_uv(id,'396ECA60A6E80E17',{0.1,0.2,0.3,0.4},5,6,7,8,9,{255,1,2,3}))
local u=last('update_bitmap_uv').args
assert(u[2]==id and u[3].id=='396ECA60A6E80E17'and u[4][1]==0.1 and u[6][3]==7,'the id second, the rest one later')
local m=screen.material('396ECA60A6E80E17',true)
assert(screen.set_texture(m,'diffuse_map','5207684C3952B0CC'))
local t=last('set_texture').args
assert(t[1]==m and t[2]=='diffuse_map'and t[3].id=='5207684C3952B0CC')
assert(not screen.bitmap_uv('XYZ',{0,0,1,1},1,1,1,1,1,{255,1,1,1}),'a name must be 16 hex digits')
assert(not screen.bitmap_uv('396ECA60A6E80E17',{0,0,2,1},1,1,1,1,1,{255,1,1,1}),'uv in 0..1')
assert(not screen.set_texture(m,'bad slot!','5207684C3952B0CC'))
assert(screen.destroy('uvbitmap',id)and last('destroy_bitmap').args[2]==id)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
