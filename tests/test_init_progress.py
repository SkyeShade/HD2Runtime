"""The Runtime's initial progress display (runtime/init_progress.lua; docs/getting-started.md "Startup progress"):
  * the percentage is the weighted sum of the real work's stages (catalogue 10, game 10, assets 25, plans 45, custom
    10), never a timer, and never 100 while a stage is pending;
  * a quick start never shows the panel; slow work shows it in the top-right after M.SHOW_AFTER s, redraws it only on a
    change (at most every M.REDRAW s), and closes it at READY (every stage done for M.SETTLE s);
  * a stage without progress for M.STALL s ends the display (READY names what is pending); late work shows it again;
  * a GUI failure disables the display for the session (logged once) and never blocks the work; a missing font only
    defers the panel;
  * logging: the initializing line, one line per stage done, one READY line; nothing per frame; the scheduler detaches
    at READY."""
import unittest

from support import run

HARNESS = r"""
local log_module=require('hd2runtime/runtime/log')
local logged={}
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local P=require('hd2runtime/runtime/init_progress');P.reset_for_tests()
local WORLD
P.hooks.game=function()return WORLD end
local CUSTOM={true,0,0}
P.hooks.custom=function()return CUSTOM[1],CUSTOM[2],CUSTOM[3]end
local FONT='core/fonts/test'
P.hooks.font=function()return FONT end
local draws,closes,opens=0,0,0
local last={}
local OPEN='ok'
P.hooks.open_screen=function(world)
    opens=opens+1
    if OPEN=='error'then error('no Ui World')end
    if OPEN=='nil'then return nil,'no Ui World yet'end
    draws=draws+1
    local texts={}
    last={texts=texts,rects=0}
    return {width=1920,height=1080,
        rect=function(x,y,layer,w,h)last.rects=last.rects+1;last.x=last.x or x;last.w=last.w or w;return 1 end,
        text=function(t)texts[#texts+1]=t;return 1 end,
        close=function()closes=closes+1 end}
end
local function frames(n,dt,each)for i=1,n do if each then each(i)end;if update then update(dt or 0.1)end end end
local function handle()return {done=false}end
local function settled(h)return h.done end
"""


class InitProgressTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body), b'ok')

    def test_the_percentage_is_the_weighted_work(self):
        self.lua(r'''
local function c(a,ad,at,p,pd,pt,cu)
    return {catalogue={fraction=1,done=1,total=1},game={fraction=1,done=1,total=1},
        assets={fraction=a,done=ad,total=at},plans={fraction=p,done=pd,total=pt},custom={fraction=cu,done=0,total=1}}
end
-- 10 + 10 + 25 * 0.5 + 45 * 0.25 + 0 = 43.75
local percent,first,label=P.progress(c(0.5,1,2,0.25,2,8,0))
assert(percent==44 and first.key=='assets'and label=='Loading asset packages (1/2)',percent..' '..label)
percent,first,label=P.progress(c(1,2,2,1,8,8,1))
assert(percent==100 and first==nil and label=='Ready')
-- Never 100 while a stage is pending.
percent,first,label=P.progress(c(1,2,2,799/800,799,800,1))
assert(percent==99 and first.key=='plans'and label=='Applying mod plans (799/800)',percent..' '..label)
-- The weights: 100 in all.
local sum=0;for _,s in ipairs(P.STAGES)do sum=sum+s.weight end
assert(sum==100 and P.STAGES[4].key=='plans'and P.STAGES[4].weight==45)
return 'ok'
''')

    def test_a_quick_start_never_shows_the_panel_and_logs_once(self):
        self.lua(r'''
WORLD={}
local h=handle()
P.start();P.track('plans',h,settled)
frames(3)
h.done=true
frames(20)
assert(draws==0 and opens==0,'the panel showed for a quick start')
assert(count('startup: initializing: 1 mod operation, 0 asset gates')==1,table.concat(logged,' | '))
assert(count('startup: READY in ')==1 and count('stage plans done in')==1,table.concat(logged,' | '))
assert(#logged==3,table.concat(logged,' | '))
assert(update==nil,'the scheduler still runs after READY')
assert(P.state().ready)
return 'ok'
''')

    def test_slow_work_shows_redraws_on_change_and_closes_at_ready(self):
        self.lua(r'''
WORLD={}
local hs={handle(),handle(),handle(),handle()}
P.start()
for _,h in ipairs(hs)do P.track('plans',h,settled)end
local shown_at
frames(80,0.1,function(i)
    if i%10==0 and hs[i/10]then hs[i/10].done=true end
    if draws>0 and not shown_at then shown_at=i end
end)
-- Shown after SHOW_AFTER (0.5 s); five pictures: 0/4, 1/4, 2/4, 3/4, then 100% Ready while it settles.
assert(shown_at and shown_at>=6 and shown_at<=7,tostring(shown_at))
assert(draws==5,'draws '..draws)
assert(last.texts[1]=='HD2Runtime 0.31'and last.texts[2]=='Initializing...'and last.texts[3]=='100%'
    and last.texts[4]=='Ready',table.concat(last.texts,'/'))
-- The top-right corner: the panel's right edge 24 units from the screen's (1080 p units).
assert(math.abs(last.x+last.w-(1920-24))<0.01,last.x..' '..last.w)
-- Closed at READY; the scheduler detached; the stage and READY lines once.
assert(closes==draws,'closes '..closes..' draws '..draws)
assert(P.state().visible==false and P.state().ready)
assert(update==nil)
assert(count('startup: stage plans done in')==1 and count('(4 of 4)')==1 and count('READY in')==1,
    table.concat(logged,' | '))
-- Each stage's time in the READY line: the plans' from the first update to the last settled (frame 40).
assert(count('READY in 5.10 s of updates (catalogue ')==1 and count('plans 3.90 s (4/4), custom 0.00 s)')==1,
    table.concat(logged,' | '))
assert(#logged==3,table.concat(logged,' | '))
return 'ok'
''')

    def test_the_stages_in_order_assets_plans_and_custom_stratagems(self):
        self.lua(r'''
WORLD={}
local gate={state='waiting'}
local h=handle()
P.start();P.track('assets',gate);P.track('plans',h,settled)
CUSTOM={false,0,2}
frames(10)
local s=P.state()
-- 10 + 10 + 0 + 0 + 0
assert(s.percent==20 and s.stage=='assets'and s.label=='Loading asset packages',s.percent..' '..s.label)
gate.state='ready'
frames(1)
s=P.state()
assert(s.percent==45 and s.stage=='plans'and s.label=='Applying mod plans',s.percent..' '..s.label)
h.done=true
frames(1)
s=P.state()
assert(s.percent==90 and s.stage=='custom'and s.label=='Preparing custom stratagems (0/2)',s.percent..' '..s.label)
CUSTOM={true,2,2}
frames(30)
assert(P.state().ready and update==nil)
assert(count('stage assets done')==1 and count('stage plans done')==1 and count('stage custom done')==1
    and count('(2 of 2)')==1,table.concat(logged,' | '))
-- A failed gate is settled work too.
P.reset_for_tests();logged={}
local g2={state='waiting'}
P.track('assets',g2)
frames(2)
g2.state='failed'
frames(20)
assert(P.state().ready and count('READY in')==1)
return 'ok'
''')

    def test_a_stall_ends_the_display_and_names_what_is_pending(self):
        self.lua(r'''
WORLD={}
local h=handle()
P.start();P.track('plans',h,settled)
frames(100,0.5)
assert(P.state().ready and update==nil)
assert(count('READY in')==1 and count('still pending, not Runtime work: Applying mod plans')==1,table.concat(logged,' | '))
assert(draws==1 and closes==1,'draws '..draws)
-- No line per frame: initializing, READY.
assert(#logged==2,table.concat(logged,' | '))
return 'ok'
''')

    def test_late_work_shows_the_panel_again(self):
        self.lua(r'''
WORLD={}
P.start()
local h=handle()
P.track('plans',h,settled)
frames(2)
h.done=true
frames(20)
assert(P.state().ready and update==nil and draws==0)
-- A mod registers late: the panel shows while it is pending, READY again (late work).
local late=handle()
P.start();P.track('plans',late,settled)
assert(not P.state().ready)
frames(20)
assert(draws>=1,'the late work did not show the panel')
late.done=true
frames(30)
assert(P.state().ready and update==nil and closes==draws)
assert(count('READY in')==2 and count('(late work)')==1,table.concat(logged,' | '))
return 'ok'
''')

    def test_a_gui_failure_disables_the_display_and_never_blocks(self):
        self.lua(r'''
WORLD={}
OPEN='error'
local h=handle()
P.start();P.track('plans',h,settled)
frames(30)
assert(opens==1 and P.state().disabled,'opens '..opens)
assert(count('the progress display is unavailable')==1 and count('no Ui World')==1,table.concat(logged,' | '))
h.done=true
frames(30)
assert(opens==1 and P.state().ready and update==nil and count('READY in')==1)
-- Not drawable yet (no font, no Ui World): deferred quietly, shown once it is.
P.reset_for_tests();logged={};opens,draws=0,0
OPEN='ok';FONT=nil
local h2=handle()
P.start();P.track('plans',h2,settled)
frames(20)
assert(draws==0 and opens==0 and#logged==1,table.concat(logged,' | '))
OPEN='nil';FONT='core/fonts/test'
frames(5)
assert(draws==0 and opens>=1 and not P.state().disabled)
OPEN='ok'
frames(5)
assert(draws==1 and not P.state().disabled)
h2.done=true
frames(30)
assert(P.state().ready and update==nil and count('unavailable')==0)
return 'ok'
''')

    def test_without_a_world_nothing_shows_and_settled_work_still_reports(self):
        self.lua(r'''
-- No work at all: READY at once, silent.
P.start()
frames(2)
assert(P.state().ready and update==nil and#logged==0)
-- Work that settles before the game world exists: READY, said so; nothing drawn.
P.reset_for_tests()
local h=handle()
P.start();P.track('plans',h,settled)
frames(3)
assert(not P.state().ready)
h.done=true
frames(5)
assert(P.state().ready and update==nil and draws==0 and opens==0)
assert(count('READY in')==1 and count('(before the game world)')==1 and count('initializing')==0,
    table.concat(logged,' | '))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
