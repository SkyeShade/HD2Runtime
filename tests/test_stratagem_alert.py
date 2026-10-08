"""The custom stratagem alert card (0.30.2, runtime/stratagem_alert.lua; docs/custom-stratagem-api.md "Readiness"):
  * a Runtime-owned card at the top right (below the startup progress panel's place), the same share of the screen at
    every resolution, never wider than 90 % of it; every line inside the card (wrapped with the fonts' own metrics);
  * the title and tag in FS Sinclair Medium, the problems and fixes in FS Sinclair, a severity accent (bar, bullets,
    FIX labels, tag); three problems listed, the rest counted; a footer;
  * the most severe card shows, the newest of equal severity first; clear() takes a card away; a card closes after
    M.SECONDS with its timer bar shrinking (update_rect); the same card is not repeated within M.REPEAT s;
  * no font yet: it waits (and is dropped after M.WAIT); a refused primitive turns the card off for the session and
    every subject goes to the safety notice panel instead;
  * read-only: no write, no transaction, no native call."""
import unittest

from support import ROOT, run

HARNESS = r"""
local card=require('hd2runtime/runtime/stratagem_alert')
local UF=require('hd2runtime/domains/ui_fonts')
local fonts=require('hd2runtime/runtime/ui_fonts')
local logged={}
require('hd2runtime/runtime/log').emit=function(text)logged[#logged+1]=text end
local function count(s)local n=0;for _,l in ipairs(logged)do if l:find(s,1,true)then n=n+1 end end;return n end
local RES={1920,1080}
local screens={}
local refuse=nil
local function setup()
    card.reset_for_tests()
    card.hooks.world=function()return {runtime={}}end
    card.hooks.fonts=function()return UF.fonts.title,UF.fonts.body end
    card.hooks.open_screen=function()
        local s={width=RES[1],height=RES[2],rects={},texts={},updates={},open=true}
        function s.rect(x,y,layer,w,h,c)
            if refuse=='rect'then return nil end
            s.rects[#s.rects+1]={x=x,y=y,layer=layer,w=w,h=h,c=c};return #s.rects end
        function s.update_rect(id,x,y,layer,w,h,c)s.updates[#s.updates+1]={id=id,w=w};s.rects[id].w=w;return true end
        function s.text(text,font,size,material,x,y,layer,c)
            s.texts[#s.texts+1]={s=text,font=font,size=size,x=x,y=y,layer=layer,c=c};return 1000+#s.texts end
        function s.close()s.open=false end
        screens[#screens+1]=s
        return s
    end
end
setup()
local function frames(n,dt)for _=1,n do card.tick_for_tests(dt or 0.1)end end
local function last()return screens[#screens]end
local function texts(s)local t={};for _,x in ipairs(s.texts)do t[#t+1]=x.s end;return table.concat(t,' | ')end
local READINESS={key='readiness',severity='warn',title='Custom stratagems',tag='Check before launch',
    items={{line='1 player without HD2Runtime: your custom slots will be locked.',
        fix='Fix: everyone needs the same mods (or play Friends Only), or pick vanilla.'}},
    footer='Shown again every minute while it stands.'}
"""


def lua(body):
    return run(HARNESS + body + "\nreturn 'ok'")


class AlertCardTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_card_shows_the_problem_and_its_fix_in_the_native_typeface_with_a_severity_accent(self):
        self.check(r"""
assert(card.post(READINESS))
frames(1)
local s=assert(last(),'drawn')
assert(texts(s)=='CHECK BEFORE LAUNCH | CUSTOM STRATAGEMS | 1 player without HD2Runtime: your custom slots will be '
    ..'locked. | FIX | everyone needs the same mods (or play Friends Only), or pick vanilla. | Shown again every minute '
    ..'while it stands.',texts(s))
-- the title and tag in FS Sinclair Medium, the rest in FS Sinclair
assert(s.texts[1].font==UF.fonts.title.name and s.texts[2].font==UF.fonts.title.name and s.texts[4].font==UF.fonts.title.name)
assert(s.texts[3].font==UF.fonts.body.name and s.texts[5].font==UF.fonts.body.name)
-- the accent (warn: amber) on the bar, the tag and the FIX label; the plate the native details panel's dark grey
local A=card.COLOURS.accent.warn
local function same(c,d)return c[1]==d[1]and c[2]==d[2]and c[3]==d[3]and c[4]==d[4]end
assert(same(s.rects[1].c,card.COLOURS.plate)and same(s.rects[3].c,A)and same(s.texts[1].c,A)and same(s.texts[4].c,A))
-- layers: the plate 935, its edge and bars 936, the text 937 (above the safety notice 930, below the slot overlay 940)
assert(s.rects[1].layer==935 and s.rects[3].layer==936 and s.texts[3].layer==937)
-- a failure is red
card.post({key='readiness',severity='fail',title='Custom stratagems',tag='Will fail',items=READINESS.items},true)
frames(1)
assert(same(last().rects[3].c,card.COLOURS.accent.fail),'red for a failure')
assert(not screens[#screens-1].open,'the replaced card is closed')
""")

    def test_the_same_share_of_the_screen_at_every_resolution_top_right_and_every_line_inside(self):
        self.check(r"""
local five={}
for i=1,5 do five[i]={line=('Problem number %d: a long line that has to wrap onto a second line on the card because '
    ..'it is long.'):format(i),fix='Fix: a fix line that is long enough to wrap onto a second line on the card as well.'}end
local results={}
for _,res in ipairs({{1920,1080},{2560,1440},{3440,1440},{3840,2160},{1280,720},{800,1080}})do
    RES=res;setup()
    card.post({key='readiness',severity='warn',title='Custom stratagems',tag='Check',items=five,footer='Footer.'})
    frames(1)
    local s=assert(last())
    local W,H,p=res[1],res[2],s.rects[1]
    assert(p.x>0 and p.x+p.w<W and p.y>0 and p.y+p.h<H,'on screen at '..W..'x'..H)
    assert(p.x+p.w/2>W/2 and p.y+p.h/2>H/2,'top right')
    assert(H-(p.y+p.h)>=(24+84)*(H/1080)-0.01,'below the startup progress panel place')
    assert(p.w<=W*0.9+0.01,'never wider than 90 % of the screen')
    for _,t in ipairs(s.texts)do
        local font=t.font==UF.fonts.title.name and UF.fonts.title or UF.fonts.body
        assert(t.x>=p.x and t.x+fonts.width(font,t.s,t.size)<=p.x+p.w+0.01,'inside: '..t.s)
        assert(t.y>=p.y and t.y<=p.y+p.h,'inside vertically: '..t.s)
    end
    -- three problems listed (each wrapped to two lines at most), the other two counted
    assert(texts(s):find('Problem number 3',1,true)and not texts(s):find('Problem number 4',1,true))
    assert(texts(s):find('+2 more in the HD2Runtime log',1,true),texts(s))
    results[#results+1]={W=W,H=H,w=p.w,h=p.h}
end
for k=1,5 do
    local r=results[k]
    assert(math.abs(r.w/r.H-520*card.SCALE/1080)<1e-6 and math.abs(r.h/r.H-results[1].h/1080)<1e-6,
        ('%dx%d: %.4f'):format(r.W,r.H,r.w/r.H))
end
assert(results[6].w<=800*0.9+0.01,'a narrow screen: capped at 90 %')
""")

    def test_the_most_severe_card_shows_clear_takes_it_away_and_it_closes_after_its_seconds(self):
        self.check(r"""
card.post(READINESS)
card.post({key='disabled',severity='fail',title='Custom stratagems',tag='Disabled',
    items={{line='Incompatible custom-stratagem mods detected in the lobby.'}}})
frames(1)
assert(card.status().key=='disabled'and texts(last()):find('DISABLED',1,true),'the failure first')
card.clear('disabled')
frames(1)
assert(card.status().key=='readiness'and texts(last()):find('CHECK BEFORE LAUNCH',1,true),'then the warning')
-- the timer bar shrinks while it shows, then the card closes
local s=last()
frames(math.floor(card.SECONDS/0.1/2))
assert(#s.updates>0 and s.updates[#s.updates].w<s.rects[#s.rects].w+1 and math.abs(card.status().timer-0.5)<0.02,
    tostring(card.status().timer))
frames(math.floor(card.SECONDS/0.1/2)+2)
assert(not s.open and not card.status().visible and card.status().queued==0,'closed after its seconds')
-- the same card again within M.REPEAT s: not shown; forced (a changed state): shown
assert(card.post(READINESS)==false)
assert(card.post(READINESS,true)==true)
""")

    def test_no_font_waits_and_a_refused_primitive_falls_back_to_the_safety_notice(self):
        self.check(r"""
card.hooks.fonts=function()return nil,'the engine font is not loaded'end
card.post(READINESS)
frames(10)
assert(#screens==0 and card.status().queued==1,'waits for a font')
frames(math.floor(card.WAIT/0.1)+1)
assert(card.status().queued==0,'dropped after M.WAIT (the log keeps it)')
setup()
local fallback={}
card.hooks.fallback=function(a)fallback[#fallback+1]=a.title..' '..a.tag..': '..a.items[1].line;return true end
refuse='rect'
card.post(READINESS)
frames(1)
assert(card.status().gui_disabled and#fallback==1 and fallback[1]=='Custom stratagems Check before launch: 1 player '
    ..'without HD2Runtime: your custom slots will be locked.',fallback[1])
assert(count('CUSTOM STRATAGEM ALERT: the card is unavailable')==1)
refuse=nil
card.post({key='disabled',severity='fail',title='Custom stratagems',tag='Disabled',items={{line='x'}}})
frames(1)
assert(#fallback==2,'every later subject goes to the safety notice panel')
""")

    def test_the_real_fallback_uses_the_safety_notice_panel(self):
        self.check(r"""
local got
require('hd2runtime/runtime/matchmaking_safety').notice=function(title,line,rule,advice)got={title,line,rule,advice}end
card.hooks.fallback({title='Custom stratagems',tag='Will fail',items={{line='a',fix='Fix: b'},{line='c'}},
    footer='d'})
assert(got[1]=='CUSTOM STRATAGEMS - WILL FAIL'and got[2]=='a (+1 more in the log)'and got[3]=='Fix: b'and got[4]=='d')
""")

    def test_read_only(self):
        source = (ROOT / 'runtime' / 'stratagem_alert.lua').read_text(encoding='utf-8')
        for word in ('guarded_transaction', 'windows_write', '.write(', 'ffi', 'native_call'):
            self.assertNotIn(word, source)


if __name__ == '__main__':
    unittest.main()
