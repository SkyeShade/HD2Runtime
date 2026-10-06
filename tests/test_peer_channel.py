"""The Runtime-to-Runtime peer channel (runtime/peer_channel.lua; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md
section 2; research/peer-messaging-F5FEE03DCFDB.json): the game's PlayFab lobby member data through the engine table's
two member-data slots, on the offline event world (tests/event_world_fixture.lua W.lobby). The two engine calls are
recorded, never executed. Every guard refuses before a call; posts follow the join delay, the interval, the
unchanged rule and the failure limit; reads are bounded copies of printable text, members only."""
import json
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE

RESEARCH = json.loads((ROOT / 'research/peer-messaging-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

HARNESS = PRELUDE + r"""
local channel=require('hd2runtime/runtime/peer_channel')
local PM=require('hd2runtime/domains/peer_messaging')
local scheduler=require('hd2runtime/runtime/scheduler')
channel.reset_for_tests()
local R=W.runtime
W.players({{peer=LOCAL,avatar=100}},LOCAL)
-- Runs fn inside the Runtime's own update (where the channel's calls may run) and returns its results.
local function in_update(fn)
    local out
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick()out={fn()};watch.status='complete'end
    scheduler.attach(watch);tick()
    return unpack(out)
end
local function world()return assert(world_module.open())end
local function seconds(s)tick(math.floor(s/0.125+0.5))end
local VALUE='hd2rt/1;0.30.0-dev;811C9DC5;1;-,-,-,-'
"""


class PeerMessagingResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges'], RESEARCH['nativeCalls']), (0, 0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['snapshots']), 7)
        for snap in RESEARCH['snapshots']:
            # [O] every retained lobby is joined and its one member is the Runtime's own session peer id.
            self.assertTrue(snap['localIsMember'])
            self.assertEqual(snap['members'], [snap['localPeer']])
            self.assertEqual((snap['playfabState'], snap['engineLobbyState'], snap['active']), (3, 3, 1))
            self.assertEqual((snap['setMemberData'], snap['memberData']), (0x8C7010, 0x8C6F30))
        self.assertEqual(len(RESEARCH['missionLobbyIds']), 1)       # one lobby from mission start to its end
        roles = {(p['module'], p['rva']) for rows in RESEARCH['pins'].values() for p in rows}
        self.assertIn(('game', 0x1094087), roles)                     # the game's own set_member_data call
        self.assertIn(('game', 0x1093DFC), roles)                     # its own member_data call
        self.assertIn(('game', 0x1091F76), roles)                     # the leave clears the flag
        self.assertIn(('exe', 0x8C7042), roles)                       # async context NULL
        self.assertIn(('exe', 0x8CDFA5), roles)                       # joined == 3
        self.assertEqual(sorted(RESEARCH['gameKeys']), ['crossplay_mode', 'platform_lobby'])
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_peer_messaging
        self.assertEqual(generate_peer_messaging.generate(check=True), [])


class PeerChannelTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_the_lobby_resolves_from_the_game_objects_with_the_local_peer_among_its_members(self):
        self.lua(r"""
W.lobby({members={OTHER,LOCAL},id='cv2:abc-123'})
local lobby=assert(channel.lobby(world()))
assert(lobby.id=='cv2:abc-123'and#lobby.members==2 and lobby.local_peer==LOCAL)
assert(lobby.members[1].peer==OTHER and not lobby.members[1]['local']and lobby.members[2]['local'])
assert(channel.KEY=='hd2rt')
for _,k in ipairs(PM.gameKeys)do assert(k~=channel.KEY,'never one of the game\'s own keys')end
""")

    def test_every_lobby_guard_refuses_before_a_call(self):
        self.lua(r"""
local function refuses(spec,code)
    W.lobby(spec)
    local l,c,why=channel.lobby(world())
    assert(l==nil and c==code,('%s: %s %s'):format(code,tostring(c),tostring(why)))
    local p,pc=in_update(function()return channel.poll(world())end)
    assert(p==nil and pc==code)
end
refuses({active=false},'NOT_JOINED')                 -- the game's own condition: the wrapper's flag
refuses({engine=false},'NOT_JOINED')
refuses({state=4},'NOT_JOINED')                      -- left or failed
refuses({handle=false},'NOT_JOINED')
refuses({members={OTHER}},'NOT_MEMBER')
refuses({members={}},'UNREADABLE')
assert(#R.lobby_reads==0 and#R.lobby_posts==0,'no call was made')
""")

    def test_the_build_table_thread_and_adapter_guards(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
-- Outside the Runtime's update: refused.
local p,c=channel.poll(world())
assert(p==nil and c=='NOT_GAME_THREAD')
-- A slot that is not the pinned engine function.
W.lobby({members={LOCAL,OTHER},slots=false})
p,c=in_update(function()return channel.poll(world())end)
assert(p==nil and c=='UNSUPPORTED_BUILD')
W.lobby({members={LOCAL,OTHER}})
-- An adapter that cannot call game functions.
local read=R.native_lobby_read;R.native_lobby_read=nil
p,c=in_update(function()return channel.poll(world())end)
assert(p==nil and c=='UNAVAILABLE');R.native_lobby_read=read
-- A changed pin (the game's own member_data call site).
channel.reset_for_tests()
W.write(W.GAME+0x1093DFC,'\144\144')
p,c=in_update(function()return channel.poll(world())end)
assert(p==nil and c=='UNSUPPORTED_BUILD')
assert(#R.lobby_reads==0,'no read was made')
""")

    def test_reads_are_members_only_bounded_printable_copies(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER,'9999AAAABBBBCCCC'}})
W.lobby_values[OTHER]='hd2rt/1;0.30.0-dev;811C9DC5;4;orbital_gas_barrage,-,-,-'
W.lobby_values['9999AAAABBBBCCCC']=string.rep('x',600)               -- longer than the channel's 512 bytes
W.lobby_values[LOCAL]=VALUE
W.lobby_values['DDDDEEEEFFFF0000']='not a member'
local p=assert(in_update(function()return channel.poll(world())end))
assert(#p.values==2,'this machine\'s own value only on request')
assert(p.values[1].peer==OTHER and p.values[1].value=='hd2rt/1;0.30.0-dev;811C9DC5;4;orbital_gas_barrage,-,-,-')
assert(p.values[2].value==nil and p.values[2].error:find('longer than 512'))
W.lobby_values['9999AAAABBBBCCCC']='bad\1byte'
p=in_update(function()return channel.poll(world(),{include_local=true})end)
assert(#p.values==3 and p.values[1]['local']and p.values[1].value==VALUE)
assert(p.values[3].value==nil and p.values[3].error=='not printable ASCII')
W.lobby_values[OTHER]=nil
p=in_update(function()return channel.poll(world())end)
assert(p.values[1].value==nil and p.values[1].error==nil,'no property: nil')
for _,r in ipairs(R.lobby_reads)do assert(r.key=='hd2rt'and r.peer~='DDDDEEEEFFFF0000')end
""")

    def test_posts_wait_for_the_join_delay_then_follow_the_interval_and_never_repeat(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
local r=channel.publish(VALUE)                     -- outside the update: it waits for the channel's own watch
assert(r.status=='deferred'and r.code=='NOT_GAME_THREAD')
seconds(5)
assert(#R.lobby_posts==0,'nothing in the first 10 s of a lobby')
seconds(5.5)
assert(#R.lobby_posts==1 and R.lobby_posts[1].key=='hd2rt'and R.lobby_posts[1].value==VALUE)
assert(W.lobby_values[LOCAL]==VALUE and count('PEER CHANNEL POSTED')==1)
-- The same value again: never posted twice.
r=in_update(function()return channel.publish(VALUE)end)
assert(r.status=='unchanged')
-- A new value right after a post waits for the 5 s interval.
local v2='hd2rt/1;0.30.0-dev;811C9DC5;2;-,-,-,-'
r=in_update(function()return channel.publish(v2)end)
assert(r.status=='deferred'and r.code=='RATE')
seconds(2);assert(#R.lobby_posts==1)
seconds(3.5);assert(#R.lobby_posts==2 and R.lobby_posts[2].value==v2)
-- Several changes inside one interval: only the last is posted.
in_update(function()channel.publish('hd2rt/1;0.30.0-dev;811C9DC5;3;-,-,-,-')end)
in_update(function()channel.publish('hd2rt/1;0.30.0-dev;811C9DC5;4;-,-,-,-')end)
seconds(6)
assert(#R.lobby_posts==3 and R.lobby_posts[3].value:find(';4;',1,true))
seconds(10);assert(#R.lobby_posts==3,'nothing more while the value is unchanged')
-- A value the channel cannot carry is refused before anything else.
assert(channel.publish('two\nlines').code=='INVALID'and channel.publish(string.rep('a',513)).code=='INVALID')
""")

    def test_a_new_lobby_gets_the_value_again_after_its_own_join_delay(self):
        self.lua(r"""
W.lobby({members={LOCAL},id='cv2:first'})
channel.publish(VALUE);seconds(11)
assert(#R.lobby_posts==1)
W.lobby({members={LOCAL,OTHER},id='cv2:second'})   -- this machine joined another squad
seconds(5);assert(#R.lobby_posts==1)
seconds(6);assert(#R.lobby_posts==2 and R.lobby_posts[2].value==VALUE)
assert(count('PEER CHANNEL LOBBY: cv2:second')==1)
-- Leaving: nothing is called while the game is in no lobby.
W.lobby({active=false})
channel.publish('hd2rt/1;0.30.0-dev;811C9DC5;9;-,-,-,-');seconds(20)
assert(#R.lobby_posts==2 and count('PEER CHANNEL: post waiting (NOT_JOINED')==1)
""")

    def test_the_first_post_waits_for_the_games_own_platform_lobby_post(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER},platform=false})      -- the game has not made its one-shot "platform_lobby" post yet
channel.publish(VALUE);seconds(15)
assert(#R.lobby_posts==0,'the game\'s own post goes first')
W.lobby({members={LOCAL,OTHER}})                     -- the game posted it (wrapper +0x1BA7 set)
seconds(1);assert(#R.lobby_posts==1)
-- A game that never posts it: the first post goes after PLATFORM_WAIT seconds anyway.
channel.reset_for_tests();R.lobby_posts={}
W.lobby({members={LOCAL,OTHER},platform=false,id='cv2:other'})
channel.publish(VALUE);seconds(15)
assert(#R.lobby_posts==0)
seconds(6);assert(#R.lobby_posts==1)
""")

    def test_failed_posts_retry_after_the_interval_and_stop_after_three(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
W.LOBBY_RESULT=-1994169834                         -- 0x89236216, the SDK's "rate limit exceeded"
channel.publish(VALUE);seconds(11)
assert(#R.lobby_posts==1 and count('PEER CHANNEL POST FAILED (0x89236216)')==1)
seconds(30)
assert(#R.lobby_posts==3,'three attempts, five seconds apart, then none: '..#R.lobby_posts)
assert(count('nothing more is posted in this lobby')==1)
assert(W.lobby_values[LOCAL]==nil)
""")


if __name__ == '__main__':
    unittest.main()
