"""The game's own language fonts in mod overlays (research/docs/game-font-text.md; runtime/ui_fonts.lua,
runtime/mod_overlay.lua, runtime/engine_gui.lua, scripts/hd2_font.py, scripts/generate_ui_fonts.py):
  * text is split into runs: the role font draws every character it has (text it covers is one run, unchanged); a
    character it lacks goes to a resident game font that has it; nothing resident leaves the old '?' behaviour;
  * measuring (advances and kerning), CJK wrapping (between characters, never inside a UTF-8 sequence), the 512-byte cap;
  * the overlay draws a game run with the font named by its hash (IdString64), its Runtime material, the material's
    GUI instance pointed at the atlas after the text exists, only while the font is proven loaded this frame, and
    reopens its GUI when a font in use unloads;
  * hd2.ui.can_draw / hd2.ui.game_fonts;
  * the build: one Runtime material per game font (monaco's bytes, the placeholder texture), the placeholder, the
    kerning table and the placement measured on an atlas."""
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

from support import ROOT, run
from test_ui_overlay import HARNESS

sys.path.insert(0, str(ROOT / 'scripts'))
import hd2_font  # noqa: E402

GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data\bundles.nxa')

FONTS = r'''
local F=require('hd2runtime/runtime/ui_fonts')
F.reset_for_tests()
local D=require('hd2runtime/domains/ui_fonts')
local function entry(key)for _,e in ipairs(D.game)do if e.key==key then return e end end end
local ZH=assert(F.game_font(entry('zh_hans')))
local KO=assert(F.game_font(entry('ko')))
local RU=assert(F.game_font(entry('ru')))
local BODY=D.fonts.body
local function texts(runs)local t={};for i,r in ipairs(runs)do t[i]=r.text end;return table.concat(t,'|')end
local function valid_utf8(s)
    local i=1
    while i<=#s do
        local n=F.char_length(s,i)
        if n==1 and s:byte(i)>=0x80 then return false end
        i=i+n
    end
    return true
end
'''


class RunTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + FONTS + body), b'ok')

    def test_the_generated_game_fonts_load(self):
        self.lua(r'''
assert(#D.game==6)
for _,e in ipairs(D.game)do
    local f=assert(F.game_font(e),e.key)
    local n=0;for _ in pairs(f.advances)do n=n+1 end
    assert(n==e.glyphs,e.key..' '..n)
    assert(f.name=='#'..e.font and #f.name==17 and f.material=='hd2runtime_fonts/game/'..e.key and f.em==32)
    assert(f.drop==0,'the game fonts draw their baseline at the y given')
end
assert(ZH.advances[0x4E2D]and ZH.advances[0x6587],'zh_hans has 中 and 文')
assert(KO.advances[0xD55C],'ko has 한')
assert(RU.advances[0x0416]and RU.kerning,'ru has Ж and kerning pairs')
assert(not BODY.advances[0x4E2D]and BODY.advances[65],'FS Sinclair has Latin, not CJK')
return 'ok'
''')

    def test_runs_keep_latin_in_the_role_font(self):
        self.lua(r'''
-- Text the role font fully covers: one run, the role font, whatever is resident.
local r=F.runs(BODY,'Hello, world',{ZH})
assert(#r==1 and r[1].font==BODY and r[1].text=='Hello, world')
-- Mixed: Latin in FS Sinclair, the CJK phrase (with its inner space) in the game font.
r=F.runs(BODY,'Score 中文 测试 OK',{ZH})
assert(texts(r)=='Score |中文 测试 |OK',texts(r))
assert(r[1].font==BODY and r[2].font==ZH and r[3].font==BODY)
-- The pieces are byte-exact and in order.
local all={};for i,x in ipairs(r)do all[i]=x.text end
assert(table.concat(all)=='Score 中文 测试 OK')
-- No game font resident: one run in the role font (the engine draws its '?'), exactly today's behaviour.
r=F.runs(BODY,'Score 中文',{})
assert(#r==1 and r[1].font==BODY)
r=F.runs(BODY,'Score 中文',nil)
assert(#r==1 and r[1].font==BODY)
-- A character no resident font has stays with the role font.
r=F.runs(BODY,'中Ω文',{ZH})
assert(texts(r)=='中|Ω|文'and r[2].font==BODY,texts(r))
-- The first resident font that has a character wins (the Korean font has a few ideographs, 中 among them).
assert(KO.advances[0x4E2D]and not KO.advances[0x6D4B])
r=F.runs(BODY,'한글 中测',{KO,ZH})
assert(r[1].font==KO and texts(r)=='한글 中|测'and r[2].font==ZH,texts(r))
return 'ok'
''')

    def test_measuring_uses_each_runs_font_and_kerning(self):
        self.lua(r'''
local size=20
local w=F.measure(BODY,'AB中文',size,{ZH})
local expect=F.width(BODY,'AB',size)+F.width(ZH,'中文',size)
assert(math.abs(w-expect)<1e-9)
assert(math.abs(F.width(ZH,'中文',size)-(ZH.advances[0x4E2D]+ZH.advances[0x6587])*size/32)<1e-9)
-- Kerning: the engine adds the pair's value to the advance (exe 0x173490); a fake pair on a copy of the font.
local k=setmetatable({kerning={[65*F.KERN_KEY+86]=-2}},{__index=ZH})
assert(math.abs(F.width(k,'AV',32)-(ZH.advances[65]+ZH.advances[86]-2))<1e-9)
assert(math.abs(F.width(k,'VA',32)-(ZH.advances[65]+ZH.advances[86]))<1e-9,'only the pair in order')
-- Without game fonts the measure is today's width.
assert(F.measure(BODY,'Hello',size,nil)==F.width(BODY,'Hello',size))
-- drawable: what would show as '?'
local ok,n,sample=F.drawable(BODY,'Hi 中文 Ελλάδα',{ZH})
assert(ok==false and n==5 and sample[1]=='Ε'and #sample==3,n)
assert(F.drawable(BODY,'Hi 中文',{ZH})==true)
assert(F.drawable(BODY,'中文',{})==false)
return 'ok'
''')

    def test_wrap_breaks_cjk_between_characters_and_never_inside_one(self):
        self.lua(r'''
local size=20
local cjk=string.rep('中文测试',10)                         -- 40 ideographs, no spaces
local lines=F.wrap(BODY,cjk,size,200,nil,{ZH})
assert(#lines>1)
for _,l in ipairs(lines)do
    assert(valid_utf8(l),'a line ends inside a character')
    assert(F.measure(BODY,l,size,{ZH})<=200+1e-9)
end
assert(table.concat(lines)==cjk,'nothing lost, no space added')
-- Measured with the role font alone (no game font resident) it still never cuts a character.
for _,l in ipairs(F.wrap(BODY,cjk,size,100))do assert(valid_utf8(l))end
-- Closing punctuation never starts a line.
local p=F.wrap(BODY,'中文。中文，中文。',size,F.measure(BODY,'中文',size,{ZH})+1,nil,{ZH})
for _,l in ipairs(p)do assert(l:sub(1,3)~='。'and l:sub(1,3)~='，',l)end
-- The ellipsis drops whole characters.
local e=F.wrap(BODY,cjk,size,200,2,{ZH})
assert(#e==2 and e[2]:sub(-3)=='...'and valid_utf8(e[2]))
-- Mixed scripts: Latin words keep their spaces, CJK joins without one.
local m=F.wrap(BODY,'Press F 开始游戏 now',size,2000,nil,{ZH})
assert(#m==1 and m[1]=='Press F 开始游戏 now',m[1])
return 'ok'
''')

    def test_wrap_of_latin_text_is_unchanged(self):
        self.lua(r'''
-- The previous wrap, verbatim (0.30.3), as the reference for text without wide characters.
local function old(font,text,size,width,lines)
    local out,line={},''
    for word in tostring(text):gmatch('%S+')do
        local candidate=line==''and word or(line..' '..word)
        if F.width(font,candidate,size)<=width then line=candidate
        else
            if line~=''then out[#out+1]=line end
            line=word
            while F.width(font,line,size)>width and#line>1 do
                local cut=#line-1
                while cut>1 and F.width(font,line:sub(1,cut),size)>width do cut=cut-1 end
                out[#out+1]=line:sub(1,cut)
                line=line:sub(cut+1)
            end
        end
    end
    if line~=''then out[#out+1]=line end
    if lines and#out>lines then
        local last=out[lines]
        while#last>1 and F.width(font,last..'...',size)>width do last=last:sub(1,-2)end
        out[lines]=last..'...'
        for k=#out,lines+1,-1 do out[k]=nil end
    end
    return out
end
local samples={'The quick brown fox jumps over the lazy dog, twice.','Supercalifragilisticexpialidocious word',
    '  leading and  double  spaces ','Orbital Gas Strike: 3 uses, 120 s cooldown!','a','Wide (parenthesis) test.'}
for _,s in ipairs(samples)do
    for _,width in ipairs({40,90,150,400})do
        for _,limit in ipairs({false,1,2})do
            local a=old(BODY,s,16,width,limit or nil)
            local b=F.wrap(BODY,s,16,width,limit or nil)
            assert(#a==#b,s..' '..width)
            for i=1,#a do assert(a[i]==b[i],s..' '..width..' ['..a[i]..'] ['..b[i]..']')end
        end
    end
end
return 'ok'
''')


OVERLAY = r'''
local F=require('hd2runtime/runtime/ui_fonts')
F.reset_for_tests()
local D=require('hd2runtime/domains/ui_fonts')
local ZH
for _,e in ipairs(D.game)do if e.key=='zh_hans'then ZH=F.game_font(e)end end
local RESIDENT={zh_hans=true}
O.hooks.game_fonts=function()return RESIDENT.zh_hans and{ZH}or{}end
O.hooks.game_font_ready=function(world,font)
    if RESIDENT[font.key]then return true end
    return false,font.key..' is not loaded'
end
O.hooks.runtime=function()return {}end
stingray.IdString64={from_hex=function(h)temp=temp+16;return {kind='IdString64',hex=h}end}
stingray.Gui.material=rec('material',function(gui,name)return {material=name}end)
stingray.Material={set_texture=rec('set_texture'),set_vector4=rec('set_vector4')}
local function texts()local out={};for _,c in ipairs(calls)do if c.name=='text'then out[#out+1]=c.args end end;return out end
local function index_of(name,from)for i=from or 1,#calls do if calls[i].name==name then return i end end end
'''


class OverlayTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + OVERLAY + body), b'ok')

    def test_latin_text_takes_the_old_path_unchanged(self):
        self.lua(r'''
local ov=hd2.ui.overlay({owner='mods/t/latin'})
ov:draw(function(d)d:text('SCORE 10',10,100,{size=24})end)
frames(1)
local t=texts()
assert(#t==1 and t[1][2]=='SCORE 10'and t[1][3]==fonts.body.name and t[1][5]==fonts.body.name)
local ascent=fonts.body.ascent*24/fonts.body.em
assert(math.abs(t[1][6][2]-(1080-100-ascent+O.TEXT_DROP*24))<1e-6)
assert(called('set_texture')==0 and called('material')==0)
return 'ok'
''')

    def test_a_cjk_run_is_drawn_in_the_game_font_with_its_atlas(self):
        self.lua(r'''
local label='Score 中文'
local ov=hd2.ui.overlay({owner='mods/t/cjk'})
ov:draw(function(d)d:text(label,10,100,{size=20})end)
frames(1)
local t=texts()
assert(#t==2,'two runs: '..#t)
assert(t[1][2]=='Score 'and t[1][3]==fonts.body.name and t[1][5]==fonts.body.name)
-- the game run: the font named by its hash, the Runtime material, after the Latin run, on the same baseline
assert(t[2][2]=='中文'and type(t[2][3])=='table'and t[2][3].kind=='IdString64'and t[2][3].hex==ZH.game.font)
assert(t[2][5]=='hd2runtime_fonts/game/zh_hans')
assert(math.abs(t[2][6][1]-(10+F.width(fonts.body,'Score ',20)))<1e-9)
local latin_y=t[1][6][2]
assert(math.abs(t[2][6][2]-(latin_y-O.TEXT_DROP*20))<1e-9,'the game font draws its baseline at the y given')
-- this GUI's instance of the material is pointed at the atlas once, after the text exists
assert(called('set_texture')==1)
local s=last('set_texture').args
assert(s[1].material=='hd2runtime_fonts/game/zh_hans'and s[2]=='msdf_texture'and s[3].hex==ZH.game.atlas)
assert(index_of('text')<index_of('set_texture'))
assert(ov:status().game_fonts[1]=='zh_hans')
-- unchanged frames call nothing
local n=#calls;frames(5);assert(#calls==n,'unchanged frames make no engine call')
-- a changed CJK run updates its text with the same font and material; the atlas is not set again
label='Score 中文中文';frames(1)
assert(called('update_text')==1 and called('set_texture')==1)
local u=last('update_text').args
assert(u[3]=='中文中文'and u[4].hex==ZH.game.font and u[6]=='hd2runtime_fonts/game/zh_hans')
return 'ok'
''')

    def test_alignment_and_text_width_use_every_run(self):
        self.lua(r'''
local w
local ov=hd2.ui.overlay({owner='mods/t/align'})
ov:draw(function(d)
    w=d:text_width('AB中文',20)
    d:text('AB中文',1000,100,{size=20,align='right'})
end)
frames(1)
local expect=F.width(fonts.body,'AB',20)+F.width(ZH,'中文',20)
assert(math.abs(w-expect)<1e-9)
local t=texts()
assert(math.abs(t[1][6][1]-(1000-expect))<1e-9)
assert(math.abs(ov:text_width('AB中文',20)-expect)<1e-9,'overlay:text_width after the first frame')
return 'ok'
''')

    def test_nothing_resident_keeps_the_question_marks(self):
        self.lua(r'''
RESIDENT.zh_hans=false
local ov=hd2.ui.overlay({owner='mods/t/none'})
ov:draw(function(d)d:text('Score 中文',10,100,{size=20})end)
frames(1)
local t=texts()
assert(#t==1 and t[1][2]=='Score 中文'and t[1][3]==fonts.body.name,'one item in FS Sinclair (its ? glyph)')
assert(called('set_texture')==0)
return 'ok'
''')

    def test_a_font_that_unloads_reopens_the_gui_without_it(self):
        self.lua(r'''
local ov=hd2.ui.overlay({owner='mods/t/unload'})
ov:draw(function(d)d:text('Score 中文',10,100,{size=20})end)
frames(1)
assert(called('create_screen_gui')==1 and #texts()==2)
-- a language switch: the font is gone this frame (the cached resident list may still name it)
local stale={ZH}
O.hooks.game_fonts=function()return stale end
RESIDENT.zh_hans=false
local before=#texts()
frames(1)
assert(called('destroy_gui')==1 and called('create_screen_gui')==2,'the GUI is closed first and opened again')
local after=texts()
for i=before+1,#after do assert(type(after[i][3])~='table','the unloaded font never reaches Gui.text')end
assert(ov:status().waiting_text==1 and ov:status().text_reason:find('not loaded',1,true))
-- the font is back: drawn again, the new GUI's instance pointed at the atlas again
RESIDENT.zh_hans=true
frames(1)
assert(called('set_texture')==2)
return 'ok'
''')

    def test_the_byte_cap_and_validation(self):
        self.lua(r'''
local long=string.rep('中',170)                    -- 510 bytes
local ov=hd2.ui.overlay({owner='mods/t/cap'})
ov:draw(function(d)
    d:text(long,0,100,{size=10})
    d:text(long..'中',0,200,{size=10})            -- 513 bytes: refused
end)
frames(1)
assert(#texts()==1 and texts()[1][2]==long)
assert(ov:status().refused==1 and ov:status().first_refusal=='text must be 1-512 printable bytes')
-- engine_gui: '#' and 16 hex digits is a font hash, anything else is refused before the engine
local engine_gui=require('hd2runtime/runtime/engine_gui')
local screen=assert(engine_gui.open({world='UI',max_layer=1023}))
local n=called('text')
assert(screen.text('x','#'..ZH.game.font,10,'m',1,2,3,{255,1,2,3}))
assert(last('text').args[3].hex==ZH.game.font)
assert(not screen.text('x','#XYZ',10,'m',1,2,3,{255,1,2,3}))
assert(not screen.text(string.rep('a',513),'f',10,'m',1,2,3,{255,1,2,3}))
assert(screen.text(string.rep('a',512),'f',10,'m',1,2,3,{255,1,2,3}))
stingray.IdString64=nil
local id,why=screen.text('x','#'..ZH.game.font,10,'m',1,2,3,{255,1,2,3})
assert(id==nil and why:find('from_hex',1,true)and screen.state=='open','no binding: refused, the GUI stays open')
assert(called('text')==n+2)
return 'ok'
''')

    def test_can_draw_and_game_fonts(self):
        self.lua(r'''
assert(hd2.ui.can_draw('Hello')==true)
assert(hd2.ui.can_draw('你好')==true)
local ok,n,sample=hd2.ui.can_draw('Γειά σου')
assert(ok==false and n>0 and #sample>=1)
RESIDENT.zh_hans=false
assert(hd2.ui.can_draw('你好')==false)
assert(not pcall(hd2.ui.can_draw,{}))
assert(not pcall(hd2.ui.can_draw,'x','comic'))
local list=hd2.ui.game_fonts()
assert(#list==6 and list[1].key=='default'and list[3].key=='zh_hans'and list[3].languages[1]=='cn')
for _,f in ipairs(list)do assert(f.resident==false and f.reason)end
return 'ok'
''')


PROOF = ROOT / 'proof/GameFontTextProof'


class ProofTests(unittest.TestCase):
    def test_the_proof_draws_every_line_and_logs_its_runs(self):
        import json
        from support import lua as lua_literal
        from test_event_scripting import SDK
        spec = json.loads((PROOF / 'hd2runtime.json').read_text(encoding='utf-8'))
        body = (PROOF / 'src/addon.lua').read_text(encoding='utf-8-sig')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write('):
            self.assertNotIn(forbidden, body)
        wrapped = SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body, spec['name'])
        self.assertEqual(run(HARNESS + OVERLAY + '\nlocal PROOF=' + lua_literal(wrapped.encode('utf-8')) + '\nlocal RESOURCE='
            + lua_literal(spec['resource']) + r'''
package.preload['mods/skyeshade/hd2runtime']=function()return hd2 end
rawset(_G,'CowboyBingusModLoader',{api=1,version=16})
assert(loadstring(PROOF,'@'..RESOURCE))()
frames(2)
local t=texts()
local zh,latin=0,0
for _,a in ipairs(t)do
    if type(a[3])=='table'then zh=zh+1;assert(a[3].hex==ZH.game.font and a[5]=='hd2runtime_fonts/game/zh_hans')
    else latin=latin+1 end
end
assert(zh>=3,'the Simplified Chinese line and the wrapped paragraph in the game font: '..zh)
assert(latin>=7,'every Latin part in FS Sinclair: '..latin)
assert(count('GameFontTextProof 0.1.0 GAME FONT TEXT BUILD')==1)
assert(count('game fonts loaded now: zh_hans')==1,'the state is logged once the window drew')
assert(count('[zh_hans] 简体中文：模组窗口测试')==1)
assert(count('Japanese')>=1 and count('can_draw=false')>=4)
local n=count('state (')
frames(5);assert(count('state (')==n,'logged again only when something changes')
RESIDENT.zh_hans=false;frames(2)
assert(count('state (')==n+1,'a language switch is logged')
return 'ok'
'''), b'ok')


def fake_monaco_material():
    m = bytearray(288)
    m[0:8] = bytes.fromhex('2001000001000000')
    struct.pack_into('<I', m, 0x80, 0x51C11754)
    struct.pack_into('<IQ', m, 0x88, 0x88BAC99B, 0x35FCB2056C9C789E)
    return bytes(m)


class BuildTests(unittest.TestCase):
    def test_the_game_font_material_and_the_placeholder(self):
        from hd2_archive import resource_hash
        name, material = hd2_font.game_font_material('zh_hans', fake_monaco_material())
        self.assertEqual(name, 'hd2runtime_fonts/game/zh_hans')
        self.assertEqual(struct.unpack_from('<Q', material, 0x8C)[0], resource_hash(hd2_font.GAME_FONT_PLACEHOLDER))
        base = fake_monaco_material()
        self.assertEqual(material[:0x8C] + material[0x94:], base[:0x8C] + base[0x94:], 'only the texture renamed')
        with self.assertRaisesRegex(ValueError, 'not the reviewed one'):
            hd2_font.game_font_material('x', bytes(288))
        main, gpu = hd2_font.placeholder_texture()
        self.assertEqual(main, hd2_font.texture_header(4, 4, 3))
        self.assertEqual(gpu, bytes(64 + 16 + 4), 'every texel 0: outside every glyph')

    def synthetic_font(self, kerning=()):
        """A one-glyph font ('H' 10 x 20 cell at atlas (4, 4), by -18) and its 32 x 32 atlas: the glyph ink rows 4..15
        of the cell (the edge 0.5 of the -3.2 / 1.6 encoding)."""
        n = 1
        header = struct.pack('<Q', 1) + struct.pack('<8f', 32, 40, 0, 1 / 32, 1 / 32, -3.2, 1.6, 8)
        header += struct.pack('<7f', 4, 4, 10, 20, -4, -18, 12)
        end = 0x58 + 4 * n + 28 * n
        header += struct.pack('<5I', n, 0x58, len(kerning), end, 0)
        body = struct.pack('<I', ord('H')) + struct.pack('<7f', 4, 4, 10, 20, -4, -18, 12)
        keys = b''.join(struct.pack('<Q', (a << 32) | b) for (a, b), _v in kerning)
        values = b''.join(struct.pack('<f', v) for _k, v in kerning)
        main = header + body + keys + values
        rgba = np.zeros((32, 32, 4), dtype=np.uint8)
        rgba[4 + 4:4 + 16, 4 + 2:4 + 8, :] = 255
        return main, rgba

    def test_kerning_and_placement_measured_on_an_atlas(self):
        main, rgba = self.synthetic_font(kerning=[((ord('A'), ord('V')), -1.5), ((ord('T'), ord('o')), -0.75)])
        self.assertEqual(hd2_font.kerning_pairs(main), {(65, 86): -1.5, (84, 111): -0.75})
        font = hd2_font.parse_font(main)
        fit = hd2_font.atlas_fit(font, rgba)
        self.assertEqual(fit['borderInside'], 0.0)
        top, bottom = hd2_font.ink_rows(font, rgba, ord('H'))
        self.assertAlmostEqual(top, 4.0, places=3)
        self.assertAlmostEqual(bottom, 16.0, places=3)
        # The cell's top lies (offset - by - pad) = 10 units above the y given; the ink bottom 16 below the cell top:
        # the baseline lands 6 units (6 / 32 of the size) below the y.
        placed = hd2_font.baseline_drop(font, rgba)
        self.assertAlmostEqual(placed['drop'], 6 / 32, places=3)
        self.assertAlmostEqual(placed['cap'], 12 / 32, places=3)
        # A font whose cells do not lie on the atlas is told apart.
        shifted = np.roll(rgba, 3, axis=1)
        self.assertGreater(hd2_font.atlas_fit(font, shifted)['borderInside'], 0)

    @unittest.skipUnless(GAME.is_file(), 'the installed game is absent')
    def test_the_game_fonts_are_the_reviewed_ones(self):
        import hd2_game_data
        src = hd2_font.read_game_fonts(hd2_game_data.Data())
        for key, _label, _package, _langs, _font, _atlas in hd2_font.GAME_FONTS:
            m = hd2_font.game_font_metrics(key, src[key])
            self.assertEqual(m['fit']['borderInside'], 0.0, key)
            self.assertEqual(m['drop'], 0.0, key)
        self.assertIn(0x4E2D, hd2_font.parse_font(src['zh_hans']['font'])['glyphs'])


if __name__ == '__main__':
    unittest.main()
