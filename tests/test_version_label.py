"""The build label in the bottom-left corner aboard the ship (runtime/version_label.lua; docs/getting-started.md
"Version label"), with the game state, the font and the screen GUI replaced:
  * shown only in the game's Ship state: hidden while a mission loads (PrepareMission), in a mission and while the
    ship loads again (PrepareShip); shown again aboard the ship;
  * "HD2Runtime <version>" over "Game <the proven build's 12 hex digits>", small, dim, bottom-left at the safe-area
    margin, at the lowest layer;
  * one GUI per ship visit, created when it appears and destroyed when it hides; nothing redrawn while it shows;
  * the state comes from the events engine's game_state source (required while the label exists, released on stop);
  * not drawable yet (no font, no Ui World): retried quietly; a GUI error turns it off once, logged once;
  * a reloaded Runtime closes the previous label first."""
import unittest

from support import run

HARNESS = r"""
local log_module=require('hd2runtime/runtime/log')
local logged={}
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local L=require('hd2runtime/runtime/version_label')
L.reset_for_tests()
local STATE={name='Ship',mission=false}
L.hooks.state=function()return STATE end
L.hooks.world=function()return {}end
local FONT='core/fonts/test'
L.hooks.font=function()return FONT end
local opens,closes,texts=0,0,{}
local OPEN='ok'
local W,H=1920,1080
L.hooks.open_screen=function()
    if OPEN=='error'then error('the GUI exploded')end
    if OPEN=='nil'then return nil,'no Ui World yet'end
    opens=opens+1
    return {width=W,height=H,
        text=function(t,font,size,material,x,y,layer,colour)
            texts[#texts+1]={t=t,font=font,size=size,x=x,y=y,layer=layer,colour=colour};return #texts end,
        close=function()closes=closes+1 end}
end
local function frames(n)for _=1,n do if update then update(0.1)end end end
local events=require('hd2runtime/runtime/events')
require('hd2runtime/runtime/event_sources')
local source=events.state.sources.game_state
assert(source,'the game_state source is registered')
"""


class VersionLabelTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_shown_aboard_the_ship_only_and_drawn_once_per_visit(self):
        self.lua(r"""
local metadata=require('hd2runtime/domains/metadata')
local profile=require('hd2runtime/schemas/current')
L.start()
frames(3)
assert(opens==1 and #texts==2,'one GUI, two texts '..opens..' '..#texts)
assert(texts[1].t=='Game '..profile.exe_sha:sub(1,12)and texts[2].t=='HD2Runtime '..metadata.version,
    texts[1].t..' / '..texts[2].t)
-- Small, dim, bottom-left at the safe-area margin, the lowest layer, the engine font.
assert(texts[1].x==14 and texts[1].y==14 and texts[2].y>texts[1].y and texts[1].size==18 and texts[1].layer==2
    and texts[1].colour[1]<=128 and texts[1].font==FONT,'placement')
assert(L.status()=='HD2Runtime '..metadata.version..' / Game '..profile.exe_sha:sub(1,12))
-- Nothing is redrawn while it shows.
frames(50)
assert(opens==1 and #texts==2 and closes==0)
-- The mission loads, runs, and the ship loads again: hidden throughout, once.
STATE={name='PrepareMission',mission=false};frames(3)
assert(closes==1 and L.status()==nil)
STATE={name='Mission',mission=true};frames(20)
STATE={name='PrepareShip',mission=false};frames(5)
assert(opens==1 and closes==1,'hidden while loading and in the mission')
-- Back aboard the ship: shown again (a fresh GUI).
STATE={name='Ship',mission=false};frames(3)
assert(opens==2 and closes==1 and #texts==4)
-- The title screen and no state at all: hidden.
STATE={name='TitleScreen',mission=false};frames(3)
assert(closes==2)
STATE=nil;frames(3)
assert(opens==2 and closes==2)
L.stop()
assert(update==nil or true)
""")

    def test_it_is_the_same_share_of_the_screen_at_every_resolution(self):
        self.lua(r"""
-- At each resolution: the font size and the margin as a share of the screen height are the same as at 1080p.
local function drawn(w,h)
    W,H=w,h
    L.reset_for_tests();texts={}
    L.hooks.state=function()return STATE end
    L.start();frames(3)
    L.stop()
    return texts[1]
end
local base=drawn(1920,1080)
assert(base.size==18 and base.x==14 and base.y==14,'1080p: 18 px at 14 px from the corner')
for _,r in ipairs({{3840,2160},{2560,1440},{1280,720}})do
    local t=drawn(r[1],r[2])
    assert(math.abs(t.size/r[2]-base.size/1080)<1e-9 and math.abs(t.x/r[2]-base.x/1080)<1e-9,
        r[1]..'x'..r[2]..': '..t.size)
end
assert(drawn(3840,2160).size==36 and drawn(1280,720).size==12,'4K twice the pixels, 720p two thirds')
-- An ultrawide window: by its height (the same as 1440p); a narrow tall window: by its width.
assert(drawn(3440,1440).size==24 and drawn(1080,1920).size==18*1080/1920,'ultrawide and portrait')
""")

    def test_it_uses_the_game_state_source_and_releases_it(self):
        self.lua(r"""
local function required()return source and source.required_by or 0 end
local before=required()
L.start()
assert(required()==before+1,'the label requires the game_state source')
L.start()
assert(required()==before+1,'starting twice requires it once')
L.stop()
assert(required()==before,'stop releases it')
-- The default state hook is the events engine's own game_state (what the source last polled).
package.loaded['hd2runtime/runtime/version_label']=nil
local fresh=require('hd2runtime/runtime/version_label')
events.state.game_state={name='Ship',mission=false}
assert(fresh.hooks.state()==events.state.game_state)
""")

    def test_not_drawable_yet_is_retried_quietly_and_an_error_turns_it_off_once(self):
        self.lua(r"""
OPEN='nil'
L.start()
frames(20)
assert(opens==0 and count('version label')==0,'no Ui World yet: nothing logged')
OPEN='ok';frames(3)
assert(opens==1,'drawn once the Ui World exists')
L.reset_for_tests();opens,closes,texts=0,0,{}
OPEN='error'
L.start()
frames(30)
assert(count('version label is off for this session: ')==1 and opens==0,table.concat(logged,' | '))
OPEN='ok';frames(10)
assert(opens==0,'off for the session')
""")

    def test_a_reloaded_runtime_closes_the_previous_label(self):
        self.lua(r"""
L.start();frames(3)
assert(opens==1)
-- A reload: a new module instance finds the previous label in _G and closes it before starting its own.
package.loaded['hd2runtime/runtime/version_label']=nil
local L2=require('hd2runtime/runtime/version_label')
assert(L2~=L)
L2.hooks=L.hooks
L2.start()
assert(closes==1,'the previous label closed')
frames(3)
assert(opens==2 and closes==1,'one label after the reload')
L2.stop()
assert(closes==2)
""")


if __name__ == '__main__':
    unittest.main()
