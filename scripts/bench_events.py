"""Measure the event system's per-tick cost on the game's own LuaJIT (offline, no game process).

The offline fixture world (tests/event_world_fixture.lua) is copied into FFI memory and served through a
`read_into` adapter that memcpy's like ReadProcessMemory does, so the event sources run their real FFI hot path. The
benchmark subscribes to every native event, populates N entities and players, and times update ticks: a steady tick
(no changes) and a busy tick (10 deaths and 20 damage changes). With --stats it also subscribes to the per-source
stat events (player_kill_credited, player_hit, player_damage_dealt), fills all 64 stat source blocks and, on busy
ticks, adds damage and hits under 10 sources. Offline tooling; nothing here ships.

  py scripts/bench_events.py [--entities 400] [--ticks 600] [--stats]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'scripts'))
from support import run  # noqa: E402

BENCH = r'''
rawset(_G,'EVENT_FIXTURE_CAPACITY',ENTITIES+8)
local W=(function()
''' + (ROOT / 'tests/event_world_fixture.lua').read_text(encoding='utf-8') + r'''
end)()
local ffi=require('ffi')
local events=require('hd2runtime/runtime/events')
local world_module=require('hd2runtime/runtime/event_world')
local api=require('hd2runtime/api/events')
require('hd2runtime/runtime/log').emit=function()end
local N,TICKS=ENTITIES,TICKS_COUNT
W.players({{peer='1111222233334444',avatar=2000}},'1111222233334444')
W.state(4)
W.add{entity=2000,type=W.AVATAR,unit=9000,owned=true,health=125,max=125}
W.unit(9000,1,2,3)
for i=1,N do W.add{entity=3000+i,type='0002BA767DF856F3',unit=0,health=100}end
W.mirror()
local runtime=W.runtime
world_module.set_runtime(runtime)
local mod=api.mod('mods/bench/all_events')
for _,name in ipairs({'mission_started','mission_ended','player_spawned','player_died','entity_spawned','entity_died',
 'entity_killed','entity_damaged','player_damaged','player_healed','player_fired'})do
 mod:on(name,function(e)end)
end
local STATS=STATS_ON
local K=require('hd2runtime/domains/event_natives').stats.keys
if STATS then
 for _,name in ipairs({'player_kill_credited','player_hit','player_damage_dealt'})do mod:on(name,function(e)end)end
 for block=0,63 do
  local type_hex=string.format('%016X',0x1000+block)
  for _,key in ipairs({K.projectiles_fired,K.dealt_kills,K.projectiles_hit,K.dealt_damage})do
   W.stat(10,key,1,block,type_hex)
  end
 end
end
ffi.cdef[[int QueryPerformanceCounter(int64_t *); int QueryPerformanceFrequency(int64_t *);]]
local k32=ffi.load('kernel32')
local qpc,freq=ffi.new('int64_t[1]'),ffi.new('int64_t[1]')
k32.QueryPerformanceFrequency(freq)
local function clock()k32.QueryPerformanceCounter(qpc);return tonumber(qpc[0])/tonumber(freq[0])end
for _=1,5 do update(1/60)end            -- start sources, first sight of every entity
local started=clock()
for _=1,TICKS do update(1/60)end
local steady=(clock()-started)/TICKS
-- Busy ticks: every tick 10 deaths and 20 damage changes (fixture writes happen outside the timed region).
local busy,count=0,0
for tick=1,math.min(TICKS,30)do
 for i=1,10 do W.set(3000+((tick*10+i)%N)+1,{life=2,health=0,creditor='1111222233334444'})end
 for i=1,20 do W.set(3000+((tick*20+i+5)%N)+1,{health=50})end
 if STATS then
  for i=1,10 do
   local block=(tick*10+i)%64
   local type_hex=string.format('%016X',0x1000+block)
   W.stat(10,K.dealt_damage,1+tick*100,block,type_hex);W.stat(10,K.projectiles_hit,1+tick,block,type_hex)
  end
 end
 local t0=clock();update(1/60);busy=busy+(clock()-t0);count=count+1
end
local metrics=require('hd2runtime/runtime/metrics').snapshot()
return string.format('{"entities":%d,"stats":%s,"steadyMs":%.4f,"busyMs":%.4f,"dispatched":%d,"healthScans":%d}',N,
 tostring(STATS),steady*1000,busy/count*1000,metrics.counters['events.dispatched']or 0,
 metrics.counters['events.health_scans']or 0)
'''


def bench(entities=400, ticks=600, stats=False):
    body = BENCH.replace('ENTITIES', str(entities)).replace('TICKS_COUNT', str(ticks)).replace(
        'STATS_ON', 'true' if stats else 'false')
    return json.loads(run(body))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entities', type=int, default=400)
    parser.add_argument('--ticks', type=int, default=600)
    parser.add_argument('--stats', action='store_true', help='also subscribe to the per-source stat events')
    args = parser.parse_args()
    print(json.dumps(bench(args.entities, args.ticks, args.stats), indent=1))
