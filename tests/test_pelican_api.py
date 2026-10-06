"""The public Pelican API (api/pelican.lua: hd2.pelican.spawn): a handle per request, refusals as codes (never raised),
the spawn made by the Runtime in its own next update, the handle following the Pelican (arriving, hovering, released,
held, departing, gone) and the mod's on_event callback run as that mod. Offline: the Pelican world of
tests/test_pelicans.py with the game's spawn request simulated."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS

API = r"""
local hd2=require('hd2runtime/api/hd2')
require('hd2runtime/api/pelican').reset_for_tests()
local OWNER='mods/test/pelican_api'
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + PELICANS + API + body)


class PelicanApiTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_spawn_follows_the_pelican_and_holds_it(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local seen={}
local p=hd2.pelican.spawn({position={x=10,y=20,z=5},hover=60,facing={x=0,y=2},owner=OWNER,
    on_event=function(e)seen[#seen+1]=e.kind end})
assert(p.status=='requested'and p:alive()and #spawn_calls==0)
tick()
assert(p.status=='arriving'and p.entity==9501 and #spawn_calls==1 and spawn_calls[1].fy==1 and spawn_calls[1].fx==0)
-- The anchor is the position; the spawn point 250 m back along the heading and 80 m up.
local c=spawn_calls[1]
assert(c.ax==10 and c.ay==20 and c.az==5 and c.x==10 and c.y==-230 and c.z==85)
assert(p:describe().spawn_point.y==-230 and p:state().anchor.y==20)
local st=p:state()
assert(st and st.entity==9501 and st.stage==1 and st.cargo==false)
BOMB.set_clock(T0+15000000);stage(0,6,0);stamp(0,'hoverStart',T0+15000000);tick()
assert(p.status=='hovering')
BOMB.set_clock(T0+20000000);stage(0,6,1);stamp(0,'releaseTime',T0+20000000);tick()
assert(p.status=='held'and p.held==60)
BOMB.set_clock(T0+80000000);stage(0,8,1);tick()
assert(p.status=='departing')
BOMB.set_clock(T0+94000000);tcount(0);tick()
assert(p.status=='gone'and not p:alive()and p:state()==nil)
assert(table.concat(seen,',')=='spawned,stage,hovering,released,held,stage,departing,gone',table.concat(seen,','))
local status=hd2.pelican.status()
assert(status.status=='available'and status.limits:find('host only',1,true))
assert(hd2.actions.status().pelican.api:find('hd2.pelican.spawn',1,true))
return 'ok'
''')

    def test_the_default_facing_is_from_the_local_player_toward_the_position(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local p=hd2.pelican.spawn({position={x=1000,y=0,z=0},owner=OWNER})
tick()
assert(p.status=='arriving'and #spawn_calls==1)
local c=spawn_calls[1]
assert(math.abs(c.fx*c.fx+c.fy*c.fy-1)<1e-6)
return 'ok'
''')

    def test_another_players_credit_only_for_the_orchestrators_marked_call_run_for_that_player(self):
        # The live-proven r6 attribution path: the host runs a client's Pelican call (custom_mp_calls ACCEPTED, host_call)
        # with credit_to = that player and the call context the orchestrator marked; the arm gets credit_peer = that peer.
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
local gunship=require('hd2runtime/runtime/pelican_gunship')
local armed={}
gunship.arm=function(entity,spec)armed[#armed+1]=spec;return {status='active',cancel=function()end}end
local mp=require('hd2runtime/runtime/multiplayer')
local P2='5555666677778888'
local GUN={behave_as='gatling_sentry',rate_multiplier=2,round='ap4',spread=100,recoil=false,face_target=true,
    unlimited_ammo=true}
local who={peer=P2,is_local=false}
local call={call_id='pelican_close_air_support#1@'..P2,remote=true,player_peer=P2}
mp.mark_call(call)
local p=hd2.pelican.spawn({position={x=10,y=20,z=5},hover=60,gun=GUN,credit_to=who,call=call,owner=OWNER})
assert(p.status=='requested',tostring(p.status)..' '..tostring(p.code)..' '..tostring(p.reason))
tick()
assert(#armed==1 and armed[1].credit_peer==P2,'credit_peer: '..tostring(armed[1]and armed[1].credit_peer))
-- A mod's own table naming another player (no marked call, or another player's call) is refused.
local forged={call_id='x#1',remote=true,player_peer=P2}
local q=hd2.pelican.spawn({position={x=10,y=20,z=5},gun=GUN,credit_to=who,call=forged,owner=OWNER})
assert(q.status=='refused'and q.code=='INVALID_CREDIT',tostring(q.status))
local r=hd2.pelican.spawn({position={x=10,y=20,z=5},gun=GUN,credit_to={peer='9999',is_local=false},call=call,owner=OWNER})
assert(r.status=='refused'and r.code=='INVALID_CREDIT')
return 'ok'
""")

    def test_refusals_are_handles_and_call_nothing(self):
        self.check(r'''
pworld()
BOMB.set_clock(T0)
tcount(0)
local function refused(code,opts,prepare)
    local undo=prepare and prepare()
    local p=hd2.pelican.spawn(opts)
    if p.status=='requested'then tick()end
    assert(p.status=='refused'and p.code==code,code..' expected, got '..tostring(p.status)..' '..tostring(p.code)
        ..': '..tostring(p.reason))
    assert(#spawn_calls==0,code..': the game was called')
    if undo then undo()end
end
refused('INVALID_POSITION',{owner=OWNER})
refused('INVALID_POSITION',{position={x=1,y=2},owner=OWNER})
refused('INVALID_HOVER',{position={x=1,y=2,z=3},hover=0,owner=OWNER})
refused('INVALID_HOVER',{position={x=1,y=2,z=3},hover=121,owner=OWNER})
refused('INVALID_FACING',{position={x=1,y=2,z=3},facing={x=0,y=0},owner=OWNER})
refused('INVALID_APPROACH',{position={x=1,y=2,z=3},approach={distance=-1},owner=OWNER})
refused('INVALID_APPROACH',{position={x=1,y=2,z=3},approach={height=600},owner=OWNER})
refused('INVALID_APPROACH',{position={x=1,y=2,z=3},approach=5,owner=OWNER})
refused('INVALID_CALLBACK',{position={x=1,y=2,z=3},on_event=5,owner=OWNER})
refused('NOT_IN_MISSION',{position={x=1,y=2,z=3},owner=OWNER},function()W.state(3)return function()W.state(4)end end)
refused('HOST_ONLY',{position={x=1,y=2,z=3},owner=OWNER},
    function()W.state(4,{host=false})return function()W.state(4)end end)
-- A refusal made by the Runtime in its update reaches the handle too.
refused('PELICAN_UNAVAILABLE',{position={x=1,y=2,z=3},owner=OWNER},function()register(false)return function()register(true)end end)
-- The rate: four at once per mod, then one every 4 s.
require('hd2runtime/api/pelican').reset_for_tests()
for _=1,4 do assert(hd2.pelican.spawn({position={x=1,y=2,z=3},owner=OWNER}).status=='requested')end
local fifth=hd2.pelican.spawn({position={x=1,y=2,z=3},owner=OWNER})
assert(fifth.status=='refused'and fifth.code=='RATE_LIMITED')
assert(count('pelican ('..OWNER..') refused: RATE_LIMITED')==1)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
