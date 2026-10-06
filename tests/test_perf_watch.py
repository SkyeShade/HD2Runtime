"""Which mod is slow (runtime/perf_watch.lua; docs/runtime-performance.md "Which mod is slow"), with a controlled
precise clock:
  * one call at or above M.SINGLE_CALL logs one PERFORMANCE line naming the mod and the callback; the same callback
    logs again only at twice its last logged time, at most M.SINGLE_CALL_LINES times;
  * a callback dispatched from inside another is counted once, as the inner one's (own time only);
  * a mod using at least M.SHARE per update over M.WINDOW s of game time logs one line with its heaviest callbacks, at
    most once per M.REPEAT s; a light mod logs nothing;
  * the real entry points are timed: an event listener, a timer and run_as by their mod; every scheduler watch, the
    Runtime's own by its module and an operation by its mod and id;
  * without a precise clock nothing is timed; hd2.diagnostics.performance() returns the totals;
  * the slowest-operations line of a slow startup names each operation's states."""
import unittest

from support import run

PRELUDE = r"""
local metrics=require('hd2runtime/runtime/metrics')
local perf=require('hd2runtime/runtime/perf_watch')
perf.reset_for_tests()
local log_module=require('hd2runtime/runtime/log')
local logged={}
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local T=0
metrics.set_clock(function()return T end)
-- One timed call of `seconds` own time by `owner`, keyed `key`.
local function call(owner,key,seconds,inner)
    local timed=perf.begin()
    T=T+seconds
    if inner then inner()end
    perf.finish(timed,owner,key,function(k)return tostring(k)end)
end
"""


class PerfWatchTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body + "\nreturn 'ok'"), b'ok')

    def test_a_slow_call_is_logged_once_per_doubling_and_at_most_three_times(self):
        self.lua(r"""
call('mods/a/b','event enemy_killed (subscription 4)',0.0235)
assert(count('PERFORMANCE: mod mods/a/b: event enemy_killed (subscription 4) took 23.5 ms in one call')==1,
    table.concat(logged,' | '))
call('mods/a/b','event enemy_killed (subscription 4)',0.030)        -- not twice 23.5 ms
call('mods/a/b','event enemy_killed (subscription 4)',0.002)        -- fast
assert(count('PERFORMANCE:')==1)
call('mods/a/b','event enemy_killed (subscription 4)',0.050)        -- twice: logged
call('mods/a/b','event enemy_killed (subscription 4)',0.200)        -- the third and last
call('mods/a/b','event enemy_killed (subscription 4)',1.000)
assert(count('PERFORMANCE:')==3 and count('(not logged again for it)')==1,table.concat(logged,' | '))
call('HD2Runtime','update of hd2runtime/runtime/x',0.009)
assert(count('PERFORMANCE: HD2Runtime (its own work): update of hd2runtime/runtime/x took 9.0 ms')==1)
""")

    def test_nested_calls_are_counted_once(self):
        self.lua(r"""
-- mods/outer's callback takes 1 ms itself and dispatches mods/inner's, which takes 20 ms.
call('mods/outer','outer callback',0.001,function()call('mods/inner','inner callback',0.020)end)
assert(count('mod mods/inner: inner callback took 20.0 ms')==1 and count('mods/outer')==0,table.concat(logged,' | '))
local s=perf.snapshot()
local by={}
for _,o in ipairs(s.owners)do by[o.owner]=o end
assert(math.abs(by['mods/outer'].total_seconds-0.001)<1e-9 and math.abs(by['mods/inner'].total_seconds-0.020)<1e-9)
assert(s.owners[1].owner=='mods/inner','the most time first')
""")

    def test_a_heavy_mod_is_named_per_window_and_a_light_one_is_not(self):
        self.lua(r"""
-- 10 s at 10 updates per second: mods/heavy 2 ms per update (two callbacks), mods/light 0.1 ms.
local function second()
    for _=1,10 do
        call('mods/heavy','event player_damaged (subscription 3)',0.0015)
        call('mods/heavy','timer (timer 7)',0.0005)
        call('mods/light','event mission_started (subscription 1)',0.0001)
        perf.update(0.1)
    end
end
for _=1,10 do second()end
assert(count('PERFORMANCE: mod mods/heavy used 2.0 ms per update over the last 10 s (200 calls); heaviest: event '
    ..'player_damaged (subscription 3) avg 1.5 ms max 1.5 ms, 100 calls; timer (timer 7) avg 0.5 ms')==1,
    table.concat(logged,' | '))
assert(count('mods/light')==0)
-- Again within 60 s: not repeated; after 60 s: logged again.
for _=1,10 do second()end
assert(count('mod mods/heavy used')==1)
for _=1,50 do second()end
assert(count('mod mods/heavy used')==2,table.concat(logged,' | '))
local s=perf.snapshot()
assert(s.timed==true and s.owners[1].owner=='mods/heavy'and s.owners[1].last_window.updates==100
    and s.owners[1].last_window.heaviest[1].label=='event player_damaged (subscription 3)')
""")

    def test_the_real_entry_points_are_timed_by_their_mod(self):
        self.lua(r"""
local events=require('hd2runtime/runtime/events')
local scheduler=require('hd2runtime/runtime/scheduler')
-- An event listener and a timer, through the engine's own invoke, and run_as.
local record={owner='mods/x/listener',label='subscription 9',calls=0,failures=0,consecutive=0,max_failures=25,
    state='active'}
events.invoke(record,'event enemy_killed',function()T=T+0.012 end,{},nil)
assert(count('PERFORMANCE: mod mods/x/listener: event enemy_killed (subscription 9) took 12.0 ms in one call')==1,
    table.concat(logged,' | '))
local function slow_startup()T=T+0.015 end
events.run_as('mods/x/startup',slow_startup)
assert(count('PERFORMANCE: mod mods/x/startup: the function at ')==1,table.concat(logged,' | '))
-- Scheduler watches: the Runtime's own (by its module) and an operation (by its mod and id).
local own={status='waiting'}
function own.tick()T=T+0.010 end
function own.cancel()own.status='cancelled'end
local op={status='waiting',perf_owner='mods/x/ops',perf_label='ensure my-op'}
function op.tick()T=T+0.011 end
function op.cancel()op.status='cancelled'end
scheduler.attach(own);scheduler.attach(op)
update(0.1)
assert(count('PERFORMANCE: mod mods/x/ops: ensure my-op took 11.0 ms in one call')==1,table.concat(logged,' | '))
assert(count('PERFORMANCE: HD2Runtime (its own work): update of ')==1,table.concat(logged,' | '))
own.status,op.status='complete','complete'
update(0.1)
local hd2=require('hd2runtime/api/hd2')
assert(hd2.diagnostics.performance==perf.snapshot)
""")

    def test_without_a_precise_clock_nothing_is_timed(self):
        self.lua(r"""
metrics.set_clock(function()return nil end)
call('mods/a/b','x',1)
assert(#perf.snapshot().owners==0 and count('PERFORMANCE:')==0)
""")

    def test_the_slowest_operations_line(self):
        self.lua(r"""
local a={kind='ensure',id='fast',perf_owner='mods/a'}
local b={kind='plan',id='slow',perf_owner='mods/b'}
local c={kind='patch',id='middle',perf_owner='mods/a'}
local line=perf.slowest_operations({handles={a,b,c},elapsed=41.2,
    waits={[b]={running=10,waiting_for_assets=30.5},[c]={running=12}},settled_at={[a]=0.5,[b]=40.5,[c]=12}})
assert(line=='[HD2Runtime] PERFORMANCE: the slowest operations to settle: plan slow (mods/b) after 40.5 s: running '
    ..'10.0 s, waiting_for_assets 30.5 s; patch middle (mods/a) after 12.0 s: running 12.0 s; ensure fast (mods/a) after '
    ..'0.5 s (hd2.diagnostics.performance() has every mod\'s time)',line)
""")


if __name__ == '__main__':
    unittest.main()
