"""Game font text in the Runtime's own panels (0.31.0, issue #8; runtime/game_text.lua): the custom stratagem panel's
details and tooltip, and the alert card, draw a mod's text (a custom stratagem's name, description, traits) with the
overlay's technique: Latin text exactly as before (one engine text in the role font), other characters in a loaded game
font (by hash, its Runtime material pointed at the atlas, on the role font's baseline), '?' for what no loaded font has
(and the game font package that has it is asked for); a GUI that drew game font text is redrawn when the font unloads."""
import unittest

from support import run

PRE = r'''
local F=require('hd2runtime/runtime/ui_fonts')
F.reset_for_tests()
local D=require('hd2runtime/domains/ui_fonts')
local GT=require('hd2runtime/runtime/game_text')
local function entry(key)for _,e in ipairs(D.game)do if e.key==key then return e end end end
local ZH=assert(F.game_font(entry('zh_hans')))
local BODY=D.fonts.body
local MONO=D.fonts.monaco
-- The loaded game fonts and their per-frame proof, stubbed: LOADED[key] = true.
local LOADED={}
F.resident_game_fonts=function()local t={};for _,e in ipairs(D.game)do if LOADED[e.key]then t[#t+1]=F.game_font(e)end end;return t end
F.game_font_ready=function(_,e)return LOADED[e.key]==true end
local WANTED={}
F.want=function(_,font,text)WANTED[#WANTED+1]=text end
local function screen()
    local s={calls={},textured={}}
    function s.text(str,font,size,material,x,y,layer,c)s.calls[#s.calls+1]={s=str,font=font,material=material,size=size,x=x,y=y};return #s.calls end
    function s.material(name)return {name=name}end
    function s.set_texture(instance,slot,hex)s.textured[#s.textured+1]=instance.name..'|'..slot..'|'..hex;return true end
    return s
end
'''


class GameTextTests(unittest.TestCase):
    def test_latin_is_one_text_and_cjk_takes_the_loaded_game_font(self):
        self.assertEqual(run(PRE + r'''
local ctx=GT.context({})
local sc=screen()
-- Latin: one engine text in the role font, unchanged; nothing asked, nothing textured.
assert(GT.text(ctx,sc,'Pelican Gas Support',BODY,20,100,500,7,{255,255,255,255})==1)
assert(#sc.calls==1 and sc.calls[1].font==BODY.name and sc.calls[1].y==500 and #WANTED==0 and next(ctx.used)==nil)
-- Chinese with no game font loaded: the role font draws it ('?'), and the package is asked for.
sc=screen()
GT.text(ctx,sc,'毒气鹈鹕 Gas',BODY,20,100,500,7,{255,255,255,255})
assert(#sc.calls==1 and sc.calls[1].font==BODY.name and #WANTED==1)
-- Loaded: the CJK run in the game font (by hash, its Runtime material, on the role font's baseline: the FS Sinclair
-- drop taken off), the Latin run in the role font after it; the material pointed at the atlas once per GUI.
LOADED.zh_hans=true
sc=screen()
GT.text(ctx,sc,'毒气鹈鹕 Gas',BODY,20,100,500,7,{255,255,255,255})
assert(#sc.calls==2,#sc.calls)
local drop=require('hd2runtime/runtime/mod_overlay').TEXT_DROP
assert(sc.calls[1].font=='#'..entry('zh_hans').font and sc.calls[1].material=='hd2runtime_fonts/game/zh_hans')
assert(math.abs(sc.calls[1].y-(500-drop*20))<1e-9 and sc.calls[2].font==BODY.name and sc.calls[2].y==500)
assert(math.abs(sc.calls[2].x-(100+F.width(ZH,'毒气鹈鹕 ',20)))<1e-9,sc.calls[2].x)
assert(#sc.textured==1 and sc.textured[1]=='hd2runtime_fonts/game/zh_hans|msdf_texture|'..entry('zh_hans').atlas)
GT.text(ctx,sc,'描述',BODY,20,100,450,7,{255,255,255,255})
assert(#sc.textured==1,'the material instance is textured once per GUI')
-- The width and the wrap measure what is drawn.
assert(math.abs(GT.width(ctx,BODY,'毒气鹈鹕',20)-F.width(ZH,'毒气鹈鹕',20))<1e-9)
local lines=GT.wrap(ctx,BODY,'这一段文字没有空格应该在任意两个汉字之间换行',20,120,3)
assert(#lines>=2,#lines)
-- The font unloads (a language switch): still_ready says so, naming it.
assert(GT.still_ready(ctx))
LOADED.zh_hans=nil
local ok,key=GT.still_ready(ctx)
assert(not ok and key=='zh_hans')
-- A refused engine text is returned as nil (the caller's need() reports it).
sc=screen();sc.text=function()return nil end
assert(GT.text(ctx,sc,'中文',BODY,20,0,0,7,{255,255,255,255})==nil)
return 'ok'
'''), b'ok')

    def test_alert_card_lays_out_and_redraws_without_an_unloaded_font(self):
        self.assertEqual(run(PRE + r'''
local alert=require('hd2runtime/runtime/stratagem_alert')
LOADED.zh_hans=true
local L=alert.layout({title='Custom stratagems',tag='Check before launch',severity='warn',
    items={{line='毒气鹈鹕支援: 没有空闲的载具。',fix='Fix: 选择另一个。'}}},1920,1080,D.fonts.title,BODY,
    F.resident_game_fonts())
local texts=0
for _,op in ipairs(L.ops)do if op.kind=='text'then texts=texts+1;assert(op.font_obj and op.font_obj.advances)end end
assert(texts>=4,texts)
return 'ok'
'''), b'ok')

    def test_panel_wrap_never_splits_a_character(self):
        self.assertEqual(run(r'''
local P=require('hd2runtime/runtime/custom_stratagem_panel')
local F=require('hd2runtime/runtime/ui_fonts')
local function valid(s)
    local i=1
    while i<=#s do local n=F.char_length(s,i);assert(n>=1 and i+n-1<=#s,'split UTF-8');i=i+n end
    return true
end
for _,chars in ipairs({4,5,7,9,12})do
    for _,line in ipairs(P.wrap('毒气鹈鹕支援在任意两个汉字之间换行 and Latin words too',chars,3))do assert(valid(line))end
end
local out=P.wrap('Pelican Gas Support calls a Pelican',12,2)
assert(out[1]=='Pelican Gas'and out[2]=='Support...',table.concat(out,'|'))
return 'ok'
'''), b'ok')

    def test_unsupported_counts_only_what_no_font_can_ever_draw(self):
        self.assertEqual(run(r'''
local ui=require('hd2runtime/api/ui')
local overlay=require('hd2runtime/runtime/mod_overlay')
overlay.hooks.runtime=function()return nil end
-- Every character some game font has: 0, whatever is loaded now (Chinese brackets 「」 are in the Traditional Chinese
-- and Japanese fonts, not the Simplified one).
for _,text in ipairs({'Latin only','简体中文：模组窗口测试','「设置」','모드 창','Русский','zażółć'})do
    local n=ui.unsupported(text)
    assert(n==0,text..' '..n)
end
-- Greek, and a rare ideograph no game font has: counted, with a sample.
local n,sample=ui.unsupported('αβγ 齉')
assert(n==4 and #sample==3,n)
assert(not pcall(ui.unsupported,{}),'a string')
assert(not pcall(ui.unsupported,'x','comic'),'a font role')
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
