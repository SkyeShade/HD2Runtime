"""proof/RuntimePeerHelloProof 0.1.0 (docs/research/runtime-peer-messaging-F5FEE03DCFDB.md, section 4): the proof's own
addon on the offline event world with a two-member lobby (tests/event_world_fixture.lua W.lobby; the two engine calls
recorded, the service a table). It publishes HELLO after the join delay, reads it back, logs the other member's
values, publishes the size probe only after the other's hello and its own post, posts in a mission and back on the
ship, refuses malformed values and reports incompatible ones; it writes no game memory and calls nothing itself."""
import json
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE

FOLDER = ROOT / 'proof/RuntimePeerHelloProof'

HARNESS = PRELUDE + r"""
local channel=require('hd2runtime/runtime/peer_channel')
channel.reset_for_tests()
local R=W.runtime
W.players({{peer=LOCAL,avatar=100},{peer=OTHER}},LOCAL)
W.lobby({members={LOCAL,OTHER},id='cv2:squad'})
local function seconds(s)tick(math.floor(s/0.125+0.5))end
local function probe()assert(loadstring(PROOF_ADDON,'@'..PROOF_RESOURCE))()end
local V=hd2.version_label
local function other(seq,slots)return ('hd2rt/1;%s;811C9DC5;%d;%s'):format(V,seq,slots or'-,-,-,-')end
local SIZE=table.concat({'size_probe_slot0_'..string.rep('x',31),'size_probe_slot1_'..string.rep('x',31),
    'size_probe_slot2_'..string.rep('x',31),'size_probe_slot3_'..string.rep('x',31)},',')
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class RuntimePeerHelloProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_peer_hello_proof')
        self.assertEqual(run('local PROOF_ADDON=' + lua_literal(wrapped) + '\nlocal PROOF_RESOURCE='
            + lua_literal(resource) + '\n' + HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_the_sources_touch_no_memory_and_the_build_is_named(self):
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'transaction',
                'native_lobby'):
            self.assertNotIn(forbidden, body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        self.assertIn("BUILD='0.1.0 PEER HELLO BUILD'", body)
        self.assertIn('0.1.0 PEER HELLO BUILD', (FOLDER / 'README.md').read_text(encoding='utf-8'))

    def test_hello_both_ways_the_size_probe_the_mission_and_back(self):
        self.lua(r"""
probe()
assert(count('RuntimePeerHelloProof 0.1.0 PEER HELLO BUILD')==1)
seconds(5)
assert(#R.lobby_posts==0,'nothing in the first 10 s of the lobby')
assert(count('PEER IDS: lobby members '..LOCAL..' (you), '..OTHER..'; session players '..LOCAL..' (you), '..OTHER
    ..'; every lobby member is a session player: yes')==1)
assert(count('PEER '..OTHER..': no hd2rt value yet')==1)
seconds(6)
assert(#R.lobby_posts==1 and R.lobby_posts[1].value==other(1),R.lobby_posts[1]and R.lobby_posts[1].value)
seconds(2)
assert(count('OWN VALUE VISIBLE: HELLO (seq 1)')==1)
-- The other member's hello (client -> host as much as host -> client: the channel has no direction).
W.lobby_values[OTHER]=other(1);seconds(2.5)
assert(count('PEER HELLO RECEIVED from '..OTHER)==1 and count('compatible with this machine: yes')==1)
-- 20 s after it: the size probe (the longest legal value), posted and read back; the other's arrives whole.
seconds(15);assert(#R.lobby_posts==1)
seconds(6)
assert(#R.lobby_posts==2 and R.lobby_posts[2].value==other(2,SIZE),'the size probe: '..tostring(#R.lobby_posts))
W.lobby_values[OTHER]=other(2,SIZE);seconds(2.5)
assert(count('SIZE PROBE RECEIVED WHOLE from '..OTHER..': '..#other(2,SIZE)..' bytes')==1)
-- A mission: posted 20 s in; the other's mission value read (every 5 s there).
W.state(4);seconds(2.5)
assert(count('STATE: mission')==1 and count('this machine is the host; lobby cv2:squad, 2 members')==1)
seconds(21)
assert(#R.lobby_posts==3 and R.lobby_posts[3].value==other(3),'the mission post')
W.lobby_values[OTHER]=other(3);seconds(5.5)
assert(count(' UTC, mission): seq 3')==1)
-- Back aboard the ship.
W.state(3);seconds(8)
assert(#R.lobby_posts==4 and R.lobby_posts[4].value==other(4)and count('BACK ON SHIP SET (seq 4')==1)
assert(count('PEER SEQ')==0 and count('PEER VALUE REFUSED')==0 and count('POST FAILED')==0)
assert(R.writes==nil or#R.writes==0,'no game memory written')
""")

    def test_malformed_and_incompatible_values_are_reported_never_applied(self):
        self.lua(r"""
probe();seconds(12)
W.lobby_values[OTHER]='hd2rt/1;0.31.0;811C9DC5;1;-,-,-,-';seconds(2.5)
assert(count('compatible with this machine: NO (runtime version differs: mine '..V..' / 811C9DC5)')==1)
W.lobby_values[OTHER]='hd2rt/1;'..V..';811C9DC5;5;0x7ff6086d0000,-,-,-';seconds(2.5)
assert(count('PEER VALUE REFUSED from '..OTHER)==1 and count('MALFORMED: slot 0')==1)
W.lobby_values[OTHER]='hd2rt/1;'..V..';811C9DC5;2;-,-,-,-';seconds(2.5)
assert(count('PEER SEQ REGRESSION from '..OTHER..': 2 after 1')==0,'the refused value set no counter')
W.lobby_values[OTHER]='hd2rt/1;'..V..';811C9DC5;1;-,-,-,-';seconds(2.5)
assert(count('PEER SEQ REGRESSION from '..OTHER..': 1 after 2')==1)
""")


if __name__ == '__main__':
    unittest.main()
