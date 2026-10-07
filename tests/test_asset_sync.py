"""Synced asset loading (runtime/asset_sync.lua, runtime/asset_sync_protocol.lua; docs/asset-loading.md "Synced asset
loading (development)"): a mod's shared asset gate on one machine publishes its catalog packages under the second lobby
member key `hd2as`; another machine of the same Runtime version and catalog hash requests them through core/assets.
Offline, on the event world's lobby (tests/event_world_fixture.lua W.lobby, W.lobby_keyed); the engine calls are
recorded, never executed."""
import unittest

from support import run
from test_event_scripting import PRELUDE

PROTOCOL = r"""
local P=require('hd2runtime/runtime/asset_sync_protocol')
local A,B='0089BBE3E284FCAA','7D72A031B0B3C618'
local function refuses(text,needle)
    local d,why=P.decode(text)
    assert(d==nil and tostring(why):find(needle,1,true),tostring(text)..': '..tostring(why))
end
"""

HARNESS = PRELUDE + r"""
local channel=require('hd2runtime/runtime/peer_channel')
local sync=require('hd2runtime/runtime/asset_sync')
local P=require('hd2runtime/runtime/asset_sync_protocol')
local assets=require('hd2runtime/core/assets')
local scheduler=require('hd2runtime/runtime/scheduler')
channel.reset_for_tests();sync.reset_for_tests()
local R=W.runtime
W.players({{peer=LOCAL,avatar=100}},LOCAL)
-- The package system: requests recorded; a requested package becomes resident.
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local REQUESTS={}
R.package_request=function(entry,instance,id)
    local package='0x'..(id:reverse():gsub('.',function(c)return string.format('%02X',c:byte())end))
    REQUESTS[#REQUESTS+1]=package
    R.packages[package]=nil                  -- resident from now on (the fixture's default)
end
local function seconds(s)tick(math.floor(s/0.125+0.5))end
local function hd2as_posts()
    local out={}
    for _,p in ipairs(R.lobby_posts)do if p.key=='hd2as'then out[#out+1]=p.value end end
    return out
end
-- A mod's hd2.require_assets on this machine (api/assets.lua, the public path), on the fixture's package system.
local api_assets=require('hd2runtime/api/assets')
local function mod_watch(id,target)
    return scheduler.attach(api_assets.start(R,log_module.emit,{id=id,target=target}))
end
local function value_of(packages,opts)
    opts=opts or{}
    return assert(P.encode({version=opts.version or sync.version(),catalog=opts.catalog or sync.catalog_hash(),
        seq=opts.seq or 1,packages=packages}))
end
local CATALOG=assets.catalog_ids()
local function hex(id)return id:sub(3)end
"""


class AssetSyncProtocolTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PROTOCOL + body + "\nreturn 'ok'"), b'ok')

    def test_round_trip_sorts_the_packages(self):
        self.lua(r"""
local v=assert(P.encode({version='0.30.0-dev',catalog='811C9DC5',seq=7,packages={B,A}}))
assert(v=='hd2as/1;0.30.0-dev;811C9DC5;7;'..A..','..B,v)
local d=assert(P.decode(v))
assert(d.version=='0.30.0-dev'and d.catalog=='811C9DC5'and d.seq==7 and#d.packages==2)
assert(d.packages[1]==A and d.packages[2]==B)
-- 24 packages fit in the 512 bytes.
local list={}
for i=1,24 do list[i]=string.format('%016X',i)end
local full=assert(P.encode({version=string.rep('9',32),catalog='FFFFFFFF',seq=P.MAX_SEQ,packages=list}))
assert(#full<=512 and#assert(P.decode(full)).packages==24)
""")

    def test_encode_refuses_what_the_grammar_cannot_carry(self):
        self.lua(r"""
local function no(state,needle)
    local v,why=P.encode(state)
    assert(v==nil and tostring(why):find(needle,1,true),tostring(why))
end
no({version='0.30.0 dev',catalog='811C9DC5',seq=1,packages={A}},'version')
no({version='0.30.0',catalog='811c9dc5',seq=1,packages={A}},'catalog')
no({version='0.30.0',catalog='811C9DC5',seq=0,packages={A}},'sequence')
no({version='0.30.0',catalog='811C9DC5',seq=1.5,packages={A}},'sequence')
no({version='0.30.0',catalog='811C9DC5',seq=1,packages={}},'no package')
no({version='0.30.0',catalog='811C9DC5',seq=1,packages={'0x'..A}},'invalid package')
no({version='0.30.0',catalog='811C9DC5',seq=1,packages={A:lower()}},'invalid package')
no({version='0.30.0',catalog='811C9DC5',seq=1,packages={A,A}},'duplicate')
local list={};for i=1,25 do list[i]=string.format('%016X',i)end
no({version='0.30.0',catalog='811C9DC5',seq=1,packages=list},'at most 24')
""")

    def test_decode_refuses_every_value_not_matching_exactly(self):
        self.lua(r"""
local ok='hd2as/1;0.30.0-dev;811C9DC5;3;'..A
assert(P.decode(ok))
refuses(nil,'not text')
refuses('','length')
refuses(string.rep('a',513),'length')
refuses(ok..'\1','printable')
refuses('hd2rt/1;0.30.0-dev;811C9DC5;3;-,-,-,-','not hd2as/1')
refuses('hd2as/2;0.30.0-dev;811C9DC5;3;'..A,'not hd2as/1')
refuses(ok..';extra','5 fields')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3','5 fields')
refuses('hd2as/1;;811C9DC5;3;'..A,'version')
refuses('hd2as/1;0.30 dev;811C9DC5;3;'..A,'version')
refuses('hd2as/1;0.30.0-dev;811c9dc5;3;'..A,'catalog')
refuses('hd2as/1;0.30.0-dev;811C9DC;3;'..A,'catalog')
refuses('hd2as/1;0.30.0-dev;811C9DC5;0;'..A,'sequence')
refuses('hd2as/1;0.30.0-dev;811C9DC5;03;'..A,'sequence')
refuses('hd2as/1;0.30.0-dev;811C9DC5;-3;'..A,'sequence')
refuses('hd2as/1;0.30.0-dev;811C9DC5;2147483648;'..A,'sequence')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;','invalid package')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;'..A..',','invalid package')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;0x'..A,'invalid package')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;'..A:lower(),'invalid package')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;'..A:sub(2),'invalid package')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;'..B..','..A,'ascending')
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;'..A..','..A,'ascending')
local list={};for i=1,25 do list[i]=string.format('%016X',i)end
refuses('hd2as/1;0.30.0-dev;811C9DC5;3;'..table.concat(list,','),'more than 24')
""")


class AssetSyncTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_a_mods_require_assets_publishes_its_package_under_hd2as(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
sync.start()
local watch=mod_watch('mech_arm',hd2.pickup('EAT-700 Expendable Napalm'))
local dep=watch.asset_dependencies[1]
seconds(1);assert(watch.status=='complete',watch.status)
assert(#hd2as_posts()==0,'nothing in the first 10 s of a lobby')
seconds(13)                                 -- handed to the channel at the 3 s read, then the 10 s join delay
local posts=hd2as_posts()
local expected='hd2as/1;'..sync.version()..';'..sync.catalog_hash()..';1;'..hex(dep.package)
assert(#posts==1 and posts[1]==expected,tostring(posts[1]))
assert(W.lobby_keyed.hd2as[LOCAL]==expected and W.lobby_values[LOCAL]==nil,'the hd2rt store is untouched')
assert(count('SYNCED ASSETS: publishing seq 1, 1 package(s)')==1)
assert(count(dep.name..' (for mech_arm)')==1)
assert(count('PEER CHANNEL POSTED: hd2as = "'..expected..'"')==1)
-- The same package again (another mod): the value is unchanged, never posted twice.
mod_watch('other_mod',hd2.pickup('EAT-700 Expendable Napalm'));seconds(10)
assert(#hd2as_posts()==1)
local s=sync.status()
assert(#s.shared==1 and s.shared[1].holders=='mech_arm, other_mod'and s.published==expected)
-- The catalog hash: FNV-1a of every id core/assets accepts.
assert(sync.catalog_hash()==require('hd2runtime/runtime/peer_protocol').fnv1a(table.concat(CATALOG,'\n')))
assert(#CATALOG>200 and assets.known(CATALOG[1])and not assets.known('0xFFFFFFFFFFFFFFFF'))
""")

    def test_runtime_internal_gates_are_never_published(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
sync.start()
local dep=assets.dependency_for_package(CATALOG[5])
local gate=assets.gate(R,{id='custom-gas',asset_dependencies={dep}},log_module.emit)
local w={status='waiting'};function w.cancel()end
function w.tick(dt)if gate.tick(dt)~='waiting'then w.status='complete'end end
scheduler.attach(w)
seconds(20)
assert(gate.state=='ready'and#REQUESTS==1)
assert(#sync.status().shared==0 and#hd2as_posts()==0 and count('SYNCED ASSETS: publishing')==0)
""")

    def test_a_compatible_peers_packages_are_requested_and_resident_here(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
local p1,p2=CATALOG[10],CATALOG[11]
R.packages[p1],R.packages[p2]='queued','queued'
W.lobby_keyed.hd2as={[OTHER]=value_of({hex(p1),hex(p2)})}
sync.start()
seconds(2.9);assert(#REQUESTS==0,'read every 3 s')
seconds(0.5)
assert(#REQUESTS==2 and assets.held(p1)and assets.held(p2))
seconds(1)
local n1,n2=assets.dependency_for_package(p1).name,assets.dependency_for_package(p2).name
assert(count('SYNCED ASSETS: peer '..OTHER..' (seq 1) asks for 2 package(s)')==1)
assert(count('SYNCED ASSETS: peer '..OTHER..': requesting 2 package(s) here')==1)
assert(count('SYNCED ASSETS: peer '..OTHER..': 2 package(s) resident here: ')==1)
assert(count('assets for synced-'..OTHER..' requested: 2 package(s)')==1)
assert(sync.status().peers[OTHER].state=='resident')
-- Read again and again: nothing more is requested, nothing logged twice; this machine publishes nothing.
seconds(30)
assert(#REQUESTS==2 and count('resident here')==1 and#hd2as_posts()==0)
for _,r in ipairs(R.lobby_reads)do assert(r.peer==OTHER)end
-- A new seq adds one package: only that one is requested (a new gate), the held ones skipped.
local p3=CATALOG[12]
W.lobby_keyed.hd2as[OTHER]=value_of({hex(p1),hex(p2),hex(p3)},{seq=2})
seconds(3.5)
assert(#REQUESTS==3 and REQUESTS[3]==p3)
assert(count('SYNCED ASSETS: peer '..OTHER..': already held here: '..n1..', '..n2)==1)
""")

    def test_another_version_or_catalog_an_unknown_id_and_a_malformed_value_load_nothing(self):
        self.lua(r"""
local P1,P2,P3='9999AAAABBBBCCCC','DDDDEEEEFFFF0000','0000111122223333'
W.lobby({members={LOCAL,OTHER,P1,P2,P3}})
local p=CATALOG[20]
W.lobby_keyed.hd2as={
    [OTHER]=value_of({hex(p)},{version='0.29.9'}),
    [P1]=value_of({hex(p)},{catalog='0BADC0DE'}),
    [P2]=value_of({'FFFFFFFFFFFFFFFF'}),
    [P3]='hd2as/1;'..sync.version()..';'..sync.catalog_hash()..';1;'..hex(p):lower(),
}
sync.start()
seconds(30)
assert(#REQUESTS==0,'nothing requested: '..#REQUESTS)
assert(count('SYNCED ASSETS: peer '..OTHER..' runs Runtime 0.29.9 (catalog '..sync.catalog_hash()
    ..'): its assets are not loaded here')==1)
assert(count('SYNCED ASSETS: peer '..P1..' runs Runtime '..sync.version()..' (catalog 0BADC0DE)')==1)
assert(count('SYNCED ASSETS: peer '..P2..' asks for package FFFFFFFFFFFFFFFF, unknown to this catalog: skipped')==1)
assert(count('SYNCED ASSETS: peer '..P3..' published a malformed value (invalid package id)')==1)
local s=sync.status().peers
assert(s[OTHER].state=='incompatible'and s[P1].state=='incompatible'and s[P3].state=='refused')
""")

    def test_nothing_is_read_outside_a_lobby_of_two_and_nothing_posted_while_the_set_is_empty(self):
        self.lua(r"""
sync.start()
W.lobby({members={LOCAL}})
W.lobby_keyed.hd2as={[OTHER]=value_of({hex(CATALOG[3])})}
seconds(30)
W.lobby({active=false,members={LOCAL,OTHER}})
seconds(30)
assert(#R.lobby_reads==0 and#R.lobby_posts==0 and#REQUESTS==0)
""")

    def test_the_shared_set_is_capped_and_synced_packages_keep_a_reserve_of_the_budget(self):
        self.lua(r"""
for i=1,25 do sync.note(assets.dependency_for_package(CATALOG[i]),'big_mod')end
assert(#sync.status().shared==24 and count('is not shared with the lobby: at most 24 packages')==1)
local v=assert(sync.value());assert(#v<=512 and#P.decode(v).packages==24)
sync.note({package='0xFFFFFFFFFFFFFFFF',name='x'},'m');assert(#sync.status().shared==24,'unknown ids never shared')
-- The Runtime already holds 47 packages: a peer gets one more (48 = 64 - 16), the rest is refused.
sync.reset_for_tests()
for i=1,47 do assets.request(R,assets.dependency_for_package(CATALOG[i]),'own')end
W.lobby({members={LOCAL,OTHER}})
W.lobby_keyed.hd2as={[OTHER]=value_of({hex(CATALOG[60]),hex(CATALOG[61]),hex(CATALOG[62])})}
sync.start();seconds(4)
assert(#REQUESTS==48,#REQUESTS)
assert(count('SYNCED ASSETS: peer '..OTHER..': refused ')==1 and count('16 are kept for this machine')==1)
""")

    def test_the_two_keys_share_the_post_interval(self):
        self.lua(r"""
W.lobby({members={LOCAL,OTHER}})
local at={}
local publish=R.native_lobby_publish
R.native_lobby_publish=function(...)at[#at+1]=channel.clock();return publish(...)end
sync.start()
channel.publish('hd2rt/1;0.30.0-dev;811C9DC5;1;-,-,-,-',channel.OWNER)
mod_watch('mech_arm',hd2.pickup('EAT-700 Expendable Napalm'))
seconds(11)
assert(#R.lobby_posts==1 and R.lobby_posts[1].key=='hd2rt','one post at the end of the join delay')
seconds(5)
assert(#R.lobby_posts==2 and R.lobby_posts[2].key=='hd2as')
-- Both keys change at once: the one posted least recently goes first, the other one interval later.
channel.publish('hd2rt/1;0.30.0-dev;811C9DC5;2;-,-,-,-',channel.OWNER)
local held=R.lobby_posts[2].value
local extra
for _,id in ipairs(CATALOG)do if not held:find(hex(id),1,true)then extra=id;break end end
sync.note(assets.dependency_for_package(extra),'second')
seconds(12)
assert(#R.lobby_posts==4,#R.lobby_posts)
assert(R.lobby_posts[3].key=='hd2rt'and R.lobby_posts[4].key=='hd2as')
for i=2,#at do assert(at[i]-at[i-1]>=channel.MIN_POST_INTERVAL-1e-9,('posts %d s apart'):format(at[i]-at[i-1]))end
-- The hd2rt OWNED rule is the hd2rt key's only, and an unknown key is refused.
assert(channel.publish('x',nil,'hd2rt').code=='OWNED'and channel.publish('x',nil,'hd2as').code~='OWNED')
assert(channel.publish('x',nil,'platform_lobby').code=='INVALID_KEY')
assert(select(2,channel.poll(assert(world_module.open()),{key='crossplay_mode'}))=='INVALID_KEY')
""")


if __name__ == '__main__':
    unittest.main()
