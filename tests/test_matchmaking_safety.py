"""Runtime public-matchmaking safety (runtime/matchmaking_safety.lua; research/docs/matchmaking-safety-F5FEE03DCFDB.md;
research/matchmaking-safety-F5FEE03DCFDB.json) on the offline event world (tests/event_world_fixture.lua). The game's
two functions (the privacy setter and the Quickplay stop) are SIMULATED and recorded, never executed: the simulation
does what the pinned code does (setting +0x174 and lobby key 19, 0 while an SOS Beacon is active; the Quickplay flag
cleared).

Covered: a Public setting or a host lobby advertising Open is enforced (Friends Only, or the player's own non-public
setting re-advertised) with a log line and a notice; Friends Only / Invite Only / Friends and Clan are untouched;
offline and the game's singleplayer mode are untouched; Quickplay is cancelled aboard the ship only; an SOS Beacon is
warned, never overridden; an unproven pin, no live process, an unreadable layout or an unverified call means NO call and
a loud warning; every call runs inside the Runtime's own update; the module stays out of the peer channel and the
custom multiplayer modules."""
import json
import re
import sys
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE

sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402

RESEARCH = json.loads((ROOT / 'research/matchmaking-safety-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SOURCE = (ROOT / 'runtime/matchmaking_safety.lua').read_text(encoding='utf-8')

HARNESS = PRELUDE + r"""
local safety=require('hd2runtime/runtime/matchmaking_safety')
local MS=require('hd2runtime/domains/matchmaking_safety')
local scheduler=require('hd2runtime/runtime/scheduler')
safety.reset_for_tests()
local function unhex(h)return(h:gsub('..',function(p)return string.char(tonumber(p,16))end))end
local function ptr(a)local s=W.read(a,8);local lo=s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216
    local hi=s:byte(5)+s:byte(6)*256+s:byte(7)*65536+s:byte(8)*16777216;return lo+hi*4294967296 end
local function u32at(a)local s=W.read(a,4);return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216 end
for _,pin in ipairs(MS.pins)do W.write(W.GAME+pin.rva,unhex(pin.hex))end
W.players({{peer=LOCAL,avatar=100}},LOCAL)
-- The Game object (large enough for the live settings), its state aboard the ship.
local GAME_OBJECT=W.alloc(MS.game.settings+0x200)
W.write(W.GAME+MS.game.global,W.u64(GAME_OBJECT))
local SETTINGS=GAME_OBJECT+MS.game.settings
local function game_state(v)W.write(GAME_OBJECT+MS.game.state,W.u32(v))end
game_state(MS.game.ship)
local function set_privacy(v)W.write(SETTINGS+MS.settings.privacy,W.u32(v))end
local function privacy()return u32at(SETTINGS+MS.settings.privacy)end
-- The network context the fixture made and its lobby wrapper (no lobby yet: no engine or platform lobby, flag 0).
local CTX=ptr(W.GAME+MS.context.global)
local WRAPPER=CTX+MS.context.wrapper
W.write(WRAPPER+MS.wrapper.engineLobby,W.u64(0));W.write(WRAPPER+MS.wrapper.platformLobby,W.u64(0))
W.write(WRAPPER+MS.wrapper.active,'\0')
local function key(k,text)W.write(WRAPPER+MS.wrapper.keys+k*MS.wrapper.keyStride,text..'\0')end
local function read_key(k)return(W.read(WRAPPER+MS.wrapper.keys+k*MS.wrapper.keyStride,16):match('^[^%z]*'))end
local PRIVACY_KEY,SOS_KEY=MS.lobbyKeys.privacyMode,MS.lobbyKeys.sosBeacons
key(PRIVACY_KEY,'1');key(SOS_KEY,'0')
local function singleplayer(on)W.write(CTX+MS.context.singleplayer,string.char(on and 1 or 0))end
-- The matchmaker and its Quickplay flags.
local MM=W.alloc(MS.matchmaker.quickplay+0x100)
W.write(W.GAME+MS.matchmaker.global,W.u64(MM))
local function quickplay(on,joining)W.write(MM+MS.matchmaker.quickplay,string.char(on and 1 or 0,joining and 1 or 0))end
local function quickplaying()return W.read(MM+MS.matchmaker.quickplay,1):byte()~=0 end
-- The settings descriptors (game.dll 0x11ECD60's 12 groups): group 0 holds id 7 and id 0.
local L=MS.setter.lookup
local DESCRIPTORS=W.alloc(L.stride*2)
W.write(DESCRIPTORS,W.u32(7));W.write(DESCRIPTORS+L.stride,W.u32(MS.setter.privacyId))
W.write(W.GAME+L.table,W.u64(DESCRIPTORS));W.write(W.GAME+L.counts,W.u32(2))
-- The game's two functions, simulated as the pinned code behaves, and recorded.
local calls={}
local adapter={}
function adapter.set_privacy(entry,settings,value)
    assert(entry==W.GAME+MS.setter.rva and settings==SETTINGS,'the setter through the wrong function or settings')
    assert(value==1 or value==2 or value==3,'never Open')
    assert(scheduler.in_update(),'a native call outside the Runtime\'s own update')
    calls[#calls+1]={what='privacy',value=value}
    W.write(settings+MS.settings.privacy,W.u32(value))
    local sos=read_key(SOS_KEY)
    key(PRIVACY_KEY,(sos~=''and sos~='0')and'0'or tostring(value))
    return true
end
function adapter.stop_quickplay(entry,matchmaker)
    assert(entry==W.GAME+MS.stopQuickplay.rva and matchmaker==MM,'the stop through the wrong function or matchmaker')
    assert(scheduler.in_update(),'a native call outside the Runtime\'s own update')
    calls[#calls+1]={what='quickplay'}
    W.write(matchmaker+MS.matchmaker.quickplay,'\0')
    return true
end
safety.set_adapter(adapter)
-- The notice's screen: recorded primitives.
local screens={}
safety.hooks.font=function()return 'fixture_font'end
safety.hooks.open_screen=function()
    local s={width=1920,height=1080,texts={},rects=0,open=true}
    function s.rect()s.rects=s.rects+1;return s.rects end
    function s.text(text)s.texts[#s.texts+1]=text;return #s.texts end
    function s.close()s.open=false end
    screens[#screens+1]=s
    return s
end
local function seconds(s)tick(math.floor(s/0.125+0.5))end
local function host_lobby(spec)
    spec=spec or{}
    W.lobby({members=spec.members or{LOCAL},host=spec.host,state=spec.state})
end
local function count_calls(what)local n=0;for _,c in ipairs(calls)do if c.what==what then n=n+1 end end;return n end
safety.start()
"""


class MatchmakingSafetyResearchTests(unittest.TestCase):
    def test_the_research_is_read_only_pinned_and_its_domain_is_current(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges'], RESEARCH['nativeCalls']), (0, 0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['snapshots']), 7)
        self.assertEqual(RESEARCH['privacy']['names'], ['Open', 'FriendsOnly', 'InviteOnly', 'FriendsAndClan'])
        self.assertEqual(RESEARCH['lobbyKeys']['names'][19], 'PrivacyMode')
        self.assertEqual(RESEARCH['lobbyKeys']['names'][8], 'SOSBeacons')
        self.assertEqual(RESEARCH['joinDenyReasons'][10], 'PrivacySettings')
        self.assertEqual(RESEARCH['filterOperators'][2], 'Equal')
        for snap in RESEARCH['snapshots']:
            # [O] every retained session advertises its own setting (Friends Only), no SOS Beacon, no Quickplay, and the
            # setter's descriptor for the privacy id exists.
            self.assertEqual((snap['privacySetting'], snap['lobbyKeys']['19'], snap['lobbyKeys']['8']), (1, '1', '0'))
            self.assertEqual((snap['quickplay'], snap['joining'], snap['singleplayer']), (0, 0, 0))
            self.assertEqual(snap['privacyDescriptor'], {'group': 0, 'index': 0})
            self.assertEqual(snap['countdownSeconds'], 30)
        rvas = {p['rva']: p for rows in RESEARCH['pins'].values() for p in rows}
        self.assertEqual(rvas[0x11ED820]['asm'], 'mov dword ptr [rsi + 0x174], edi')    # setter: privacy_mode
        self.assertEqual(rvas[0x11ED848]['asm'], 'call 0x10925d0')                       # setter: lobby key 19
        self.assertEqual(rvas[0x1030066]['asm'], 'mov r8d, dword ptr [rbx + 0x174]')     # "privacy_mode" writer
        self.assertEqual(rvas[0x108BCCD]['asm'], 'mov edx, 0x13')                        # join gate reads key 19
        self.assertEqual(rvas[0x133ACFC]['asm'], 'mov dword ptr [rsp + 0x20], 2')        # Quickplay: Equal ...
        self.assertEqual(rvas[0x133AD04]['asm'], 'lea r8d, [r15 + 0x12]')                # ... key 19 ...
        self.assertEqual(rvas[0x67A9F3]['asm'], 'lea edx, [r8 + 0x13]')                  # SOS forces key 19 ...
        self.assertEqual(rvas[0x67A9ED]['asm'], 'xor r8d, r8d')                          # ... to 0
        self.assertEqual(rvas[0xADFFC6]['asm'], 'call 0x11ed0b0')                        # the game's live-settings call
        self.assertEqual(rvas[0x148218E]['asm'], 'call 0x133e6e0')                       # the game's own Quickplay stop
        self.assertEqual(RESEARCH['dataPins'][0]['bytes'], '12d81e01')                   # jump table: id 0 -> case 0
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_matchmaking_safety
        self.assertEqual(generate_matchmaking_safety.generate(check=True), [])

    def test_the_module_stays_out_of_the_peer_channel_and_the_custom_multiplayer_modules(self):
        required = set(re.findall(r"require\('([^']+)'\)", SOURCE))
        self.assertEqual(required, {'hd2runtime/runtime/event_world', 'hd2runtime/runtime/scheduler',
            'hd2runtime/runtime/log', 'hd2runtime/runtime/metrics', 'hd2runtime/core/bytes',
            'hd2runtime/domains/matchmaking_safety', 'hd2runtime/runtime/windows_ffi',
            'hd2runtime/runtime/init_progress'})
        for word in ('peer_channel', 'peer_protocol', 'custom_mp', 'custom_multiplayer', 'custom_stratagems',
                'native_lobby_publish', 'native_lobby_read', 'hd2rt', 'platform_lobby', 'crossplay_mode',
                'runtime.write', 'WriteProcessMemory', 'VirtualProtect'):
            self.assertNotIn(word, SOURCE, word)


SNAPSHOT_HARNESS = r'''
local logged={}
require('hd2runtime/runtime/log').emit=function(line)logged[#logged+1]=line end
local json=require('hd2runtime/primary_mapper/json')
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
    expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
-- A read-only view of the real snapshot with a copy-on-read overlay (what a Public setting or a running Quickplay
-- would read as); nothing of the game runs and nothing is written to the snapshot.
local overlay={}
local runtime={mode='snapshot'}
for _,k in ipairs({'module','address','module_hash','system_info','query'})do
    runtime[k]=function(...)return source[k](...)end
end
function runtime.read(at,n)
    local bytes,why=source.read(at,n)
    if not bytes then return nil,why end
    for address,value in pairs(overlay)do
        if address<at+n and address+#value>at then
            local first,last=math.max(address,at),math.min(address+#value,at+n)
            bytes=bytes:sub(1,first-at)..value:sub(first-address+1,last-address)..bytes:sub(last-at+1)
        end
    end
    return bytes
end
local wm=require('hd2runtime/runtime/event_world')
wm.set_runtime(runtime)
local world=assert(wm.open())
local safety=require('hd2runtime/runtime/matchmaking_safety')
local MS=require('hd2runtime/domains/matchmaking_safety')
local scheduler=require('hd2runtime/runtime/scheduler')
safety.reset_for_tests()
local function in_update(fn)
    local out
    local w={status='active'}
    function w.cancel()w.status='cancelled'end
    function w.tick()out={fn()};w.status='complete'end
    scheduler.attach(w);update(0.1)
    return unpack(out)
end
local result={}
result.proven=safety.prove(world)
local o=assert(safety.observe(world))
result.observed={privacy=o.privacy,advertised=o.advertised,sos=o.sos_key,joined=o.joined,host=o.is_host,
    quickplay=o.quickplay,joining=o.joining,singleplayer=o.singleplayer,state=o.game_state}
-- 1. As retained (Friends Only): untouched; no live process, so the native adapter is never even created.
local r=in_update(function()return safety.check(world)end)
result.asIs={status=r.status,privacyAction=r.privacy_action and r.privacy_action.status}
-- 2. The overlay reads the setting as Public: the recorded call is the game's setter on the real settings object.
local calls={}
safety.set_adapter({set_privacy=function(entry,settings,value)
    calls[#calls+1]={what='privacy',entry=entry-world.game,settings=settings-o.game,value=value}
    overlay[settings+MS.settings.privacy]=string.char(value,0,0,0)
    return true
end,stop_quickplay=function(entry,matchmaker)
    calls[#calls+1]={what='quickplay',entry=entry-world.game,matchmaker=matchmaker==o.matchmaker}
    overlay[matchmaker+MS.matchmaker.quickplay]='\0'
    return true
end})
overlay[o.settings+MS.settings.privacy]='\0\0\0\0'
r=in_update(function()return safety.check(world)end)
result.public={status=r.status,privacyAction=r.privacy_action and r.privacy_action.status}
-- 3. The overlay reads Quickplay as running: stopped aboard the ship, refused in a mission.
overlay[o.matchmaker+MS.matchmaker.quickplay]='\1'
r=in_update(function()return safety.check(world)end)
result.quickplay={status=r.status,action=r.quickplay and r.quickplay.status,code=r.quickplay and r.quickplay.code}
result.calls=calls
result.logged=logged
return json.encode(result)
'''


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class RealSnapshotTests(unittest.TestCase):
    def run_snapshot(self, name):
        from lua_offline import execute
        from support import modules, lua
        path = build_profile.snapshot_directory() / name
        program = modules() + '\nlocal SNAPSHOT_PATH=' + lua(str(path.resolve())) + '\n' + SNAPSHOT_HARNESS
        return json.loads(execute(program.encode()))

    def test_on_a_real_ship_snapshot_friends_only_is_untouched_and_public_or_quickplay_take_the_game_functions(self):
        r = self.run_snapshot(build_profile.SNAPSHOT_NAME)
        self.assertTrue(r['proven'])
        self.assertEqual(r['observed'], {'privacy': 1, 'advertised': '1', 'sos': '0', 'joined': True, 'host': True,
            'quickplay': False, 'joining': False, 'singleplayer': False, 'state': 3})
        self.assertEqual(r['asIs'], {'status': 'safe'})
        self.assertEqual(r['public'], {'status': 'public', 'privacyAction': 'enforced'})
        self.assertEqual(r['quickplay'], {'status': 'quickplay', 'action': 'enforced'})
        self.assertEqual(r['calls'], [
            {'what': 'privacy', 'entry': 0x11ED0B0, 'settings': 0xAC3DC, 'value': 1},
            {'what': 'quickplay', 'entry': 0x133E6E0, 'matchmaker': True}])
        self.assertTrue(any('lobby privacy Public -> Friends Only (setting Public, advertised "1", host, lobby joined'
            in line for line in r['logged']))

    def test_on_a_real_mission_snapshot_quickplay_is_never_stopped_outside_the_ship(self):
        r = self.run_snapshot('F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap')
        self.assertTrue(r['proven'])
        self.assertEqual(r['observed']['state'], 4)
        self.assertEqual(r['asIs'], {'status': 'safe'})
        self.assertEqual(r['public']['privacyAction'], 'enforced')
        self.assertEqual(r['quickplay'], {'status': 'quickplay', 'action': 'refused', 'code': 'NOT_ON_SHIP'})
        self.assertEqual([c['what'] for c in r['calls']], ['privacy'])


class NativeAdapterTests(unittest.TestCase):
    def test_the_two_typed_calls_pass_exactly_the_game_arguments_and_refuse_anything_else(self):
        # The real FFI adapter against Lua callbacks standing in for the two game functions (nothing of the game runs).
        from lua_offline import execute
        from support import modules
        self.assertEqual(execute((modules() + r'''
local ffi=require('ffi')
local safety=require('hd2runtime/runtime/matchmaking_safety')
local MS=require('hd2runtime/domains/matchmaking_safety')
local A=safety.native_adapter()
local seen
local setter=ffi.cast('void (*)(void *, uint32_t, const void *)',function(settings,id,value)
    seen={settings=tonumber(ffi.cast('uintptr_t',settings)),id=id,value=ffi.cast('const uint32_t *',value)[0]}
end)
local stop=ffi.cast('void (*)(void *, uint8_t, int32_t, int32_t, uint8_t, uint8_t, uint8_t, uint8_t)',
    function(mm,on,a,b,c,d,e,f)seen={mm=tonumber(ffi.cast('uintptr_t',mm)),args={on,a,b,c,d,e,f}}end)
local set_entry,stop_entry=tonumber(ffi.cast('uintptr_t',setter)),tonumber(ffi.cast('uintptr_t',stop))
assert(A.set_privacy(set_entry,0x123450,1))
assert(seen.settings==0x123450 and seen.id==MS.setter.privacyId and seen.value==1)
assert(A.set_privacy(set_entry,0x123450,2)and seen.value==2)
assert(A.stop_quickplay(stop_entry,0x777000))
local a=seen.args
assert(seen.mm==0x777000 and a[1]==0 and a[2]==-1 and a[3]==0x7FFFFFFF and a[4]==0 and a[5]==0 and a[6]==0
    and a[7]==0)
-- Never Open, never another value, never a missing address: refused before the function runs.
seen=nil
assert(not pcall(A.set_privacy,set_entry,0x123450,0))
assert(not pcall(A.set_privacy,set_entry,0x123450,4))
assert(not pcall(A.set_privacy,set_entry,0,1))
assert(not pcall(A.stop_quickplay,stop_entry,0))
assert(seen==nil,'a refused call never reaches the function')
setter:free();stop:free()
return 'ok'
''').encode()), b'ok')


class MatchmakingSafetyTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_a_public_setting_becomes_friends_only_through_the_game_setter_with_a_log_line_and_a_notice(self):
        self.lua(r"""
set_privacy(0)
seconds(0.5)
assert(#calls==1 and calls[1].what=='privacy'and calls[1].value==1,#calls)
assert(privacy()==1 and read_key(PRIVACY_KEY)=='1')
assert(count('MATCHMAKING SAFETY ACTIVE')==1)
assert(count('MATCHMAKING SAFETY: lobby privacy Public -> Friends Only (setting Public, advertised -, host, lobby none; '
    ..'the game\'s own privacy setter, game.dll+11ED0B0')==1)
assert(count('use Friends Only / Invite Only with compatible Runtime users')==1)
local st=safety.status()
assert(st.events[1].kind=='privacy')
-- The notice: a Runtime-owned panel with the four lines, for NOTICE_SECONDS.
assert(#screens>=1 and screens[#screens].open)
local t=screens[#screens].texts
assert(t[1]=='HD2Runtime multiplayer safety'and t[2]=='Lobby privacy changed: Public -> Friends Only.')
assert(t[3]=='Public matchmaking disabled while Runtime is active.')
assert(t[4]=='Use Friends Only / Invite Only with compatible Runtime users.')
seconds(safety.NOTICE_SECONDS+1)
assert(not screens[#screens].open and safety.status().notice==nil)
-- Nothing more while it stays Friends Only.
seconds(5)
assert(#calls==1)
-- The player selects Public again (the options commit): corrected again, logged again.
set_privacy(0)
seconds(1.5)
assert(#calls==2 and privacy()==1 and count('lobby privacy Public -> Friends Only')==2)
""")

    def test_a_lagging_advertisement_is_reset_rarely_with_one_notice_and_a_new_public_choice_notices_again(self):
        # Live r5 (host): the lobby kept advertising Public after the setter and the host re-enforced (and re-noticed)
        # again and again.
        self.lua(r"""
set_privacy(0);host_lobby();key(PRIVACY_KEY,'0');key(SOS_KEY,'0')
seconds(0.5)
assert(#calls==1 and calls[1].value==1 and count('lobby privacy Public -> Friends Only (setting Public')==1)
seconds(0.5)
assert(#screens==1,'one notice drawn')
-- The game re-advertises Open every moment for 30 s while the setting stays Friends Only.
for _=1,120 do key(PRIVACY_KEY,'0');seconds(0.25)end
assert(#calls<=1+math.ceil(30/safety.READVERTISE),'re-set at most every '..safety.READVERTISE..' s: '..#calls)
assert(#calls>=3,'still re-set while it lags: '..#calls)
assert(count('lobby privacy Public -> Friends Only')==1,'never logged as a new enforcement')
assert(count('the lobby still advertised Public with the setting Friends Only: privacy set again')<=2)
assert(#screens==1,'no notice for a lagging advertisement: '..#screens)
-- The player chooses Public again: enforced at once, logged and noticed again.
key(PRIVACY_KEY,'1');set_privacy(0);key(PRIVACY_KEY,'0')
seconds(0.5)
assert(count('(Public chosen again: enforcement 2)')==1,table.concat(logged,' | '))
seconds(0.5)
assert(#screens==2,'a new Public choice is noticed: '..#screens)
-- ... and again within the repeat window: enforced, logged, the identical notice not shown again.
key(PRIVACY_KEY,'1');set_privacy(0);key(PRIVACY_KEY,'0')
seconds(1)
assert(count('(Public chosen again: enforcement 3)')==1 and #screens==2,#screens)
assert(privacy()==1)
""")

    def test_the_notice_is_twice_its_original_size_and_the_same_share_of_the_screen_at_every_resolution(self):
        # 0.30 release hardening: 2x (r6's 3x was too large), proportional to the screen height (UI scale) at 1080p,
        # 1440p, ultrawide 3440 x 1440 and 4K; bottom-right with a margin; never wider than 90 % of the screen.
        self.lua(r"""
local results={}
for _,res in ipairs({{1920,1080},{2560,1440},{3440,1440},{3840,2160},{1280,720},{800,1080}})do
    safety.reset_for_tests();safety.set_adapter(adapter);safety.start()
    safety.hooks.font=function()return 'fixture_font'end
    local rects,texts={},{}
    safety.hooks.open_screen=function()
        local s={width=res[1],height=res[2]}
        function s.rect(x,y,layer,w,h)rects[#rects+1]={x=x,y=y,w=w,h=h};return #rects end
        function s.text(text,font,size)texts[#texts+1]={size=size};return #texts end
        function s.close()end
        return s
    end
    set_privacy(0);host_lobby();key(PRIVACY_KEY,'0');key(SOS_KEY,'0')
    seconds(1)
    local W,H,p=res[1],res[2],rects[1]
    assert(p,'drawn at '..W..'x'..H)
    assert(p.x>0 and p.x+p.w<W and p.y>0 and p.y+p.h<H,'on screen with a margin at '..W..'x'..H)
    assert(p.w<=W*0.9+0.01,'never wider than 90 % of the screen')
    results[#results+1]={W=W,H=H,w=p.w,h=p.h,title=texts[1].size,right=W-(p.x+p.w)}
end
-- 16:9 and 21:9 at every size: twice the original panel (430 x 80 at 1080p) as a share of the height, the title 24 px at
-- 1080p, the same right margin share.
for k=1,5 do
    local r=results[k]
    assert(math.abs(r.h/r.H-160/1080)<1e-6 and math.abs(r.w/r.H-860/1080)<1e-6,('%dx%d: %.4f %.4f'):format(r.W,r.H,
        r.w/r.H,r.h/r.H))
    assert(math.abs(r.title/r.H-24/1080)<1e-6 and math.abs(r.right/r.H-24/1080)<1e-6)
end
-- The same share of the WIDTH at every 16:9 resolution (1080p, 1440p, 4K, 720p).
for _,k in ipairs({2,4,5})do assert(math.abs(results[k].w/results[k].W-results[1].w/results[1].W)<1e-6)end
-- A narrow screen: capped at 90 % of its width (and scaled down with it).
assert(results[6].w<=800*0.9+0.01 and results[6].h<160,results[6].w..' '..results[6].h)
""")

    def test_a_host_lobby_advertising_open_without_an_sos_beacon_is_corrected(self):
        self.lua(r"""
-- The options menu's working copy set Public: the lobby advertises "0", the live setting is still Friends Only.
set_privacy(1);host_lobby();key(PRIVACY_KEY,'0');key(SOS_KEY,'0')
seconds(0.5)
assert(#calls==1 and calls[1].value==1 and read_key(PRIVACY_KEY)=='1')
assert(count('lobby privacy Public -> Friends Only (setting Friends Only, advertised "0", host, lobby joined')==1)
-- An Invite Only player's own setting is advertised again (never changed to Friends Only).
safety.reset_for_tests();safety.set_adapter(adapter);safety.start();calls={}
set_privacy(2);key(PRIVACY_KEY,'0')
seconds(0.5)
assert(#calls==1 and calls[1].value==2 and privacy()==2 and read_key(PRIVACY_KEY)=='2')
assert(count('lobby privacy Public -> Invite Only (setting Invite Only, advertised "0"')==1)
""")

    def test_friends_only_invite_only_and_friends_and_clan_are_untouched(self):
        self.lua(r"""
for _,v in ipairs({1,2,3})do
    set_privacy(v)
    host_lobby();key(PRIVACY_KEY,tostring(v));key(SOS_KEY,'0')
    seconds(3)
    W.lobby({members={LOCAL,OTHER}})
    seconds(3)
end
assert(#calls==0 and privacy()==3)
assert(count('MATCHMAKING SAFETY ACTIVE')==1)
assert(count('lobby privacy')==0 and count('WARNING')==0 and count('UNAVAILABLE')==0)
assert(safety.status().notice==nil and #screens==0)
""")

    def test_offline_and_singleplayer_are_untouched(self):
        self.lua(r"""
-- Offline: no Game object yet. Nothing is read beyond it, called or logged.
W.write(W.GAME+MS.game.global,W.u64(0))
set_privacy(0);quickplay(true)
seconds(3)
assert(#calls==0 and count('MATCHMAKING SAFETY')==0)
-- No network context either.
W.write(W.GAME+MS.game.global,W.u64(GAME_OBJECT));W.write(W.GAME+MS.context.global,W.u64(0))
seconds(3)
assert(#calls==0 and count('MATCHMAKING SAFETY')==0)
-- The game's singleplayer mode (the host refuses every join there): untouched.
W.write(W.GAME+MS.context.global,W.u64(CTX));quickplay(false);singleplayer(true)
seconds(3)
assert(#calls==0 and count('lobby privacy')==0 and count('MATCHMAKING SAFETY ACTIVE')==1)
-- Leaving it: the Public setting is enforced then.
singleplayer(false)
seconds(1)
assert(#calls==1 and calls[1].value==1)
""")

    def test_quickplay_is_cancelled_through_the_game_stop_aboard_the_ship_only(self):
        self.lua(r"""
set_privacy(1);quickplay(true,false)
tick()
assert(#calls==1 and calls[1].what=='quickplay'and not quickplaying())
assert(count('MATCHMAKING SAFETY: Quickplay cancelled (searching; the game\'s own Quickplay stop, game.dll+133E6E0')==1)
seconds(0.5)
assert(screens[#screens].texts[2]=='Quickplay cancelled: it joins public games with strangers.')
-- Again later (after the call interval), joining phase.
seconds(1);quickplay(true,true);tick()
assert(count_calls('quickplay')==2 and count('Quickplay cancelled (joining a found lobby')==1)
-- Not aboard the ship: never called, warned once.
seconds(1);game_state(4);quickplay(true,false)
seconds(2)
assert(count_calls('quickplay')==2 and quickplaying())
assert(count('Quickplay is running (searching) and cannot be cancelled (NOT_ON_SHIP')==1)
""")

    def test_an_sos_beacon_is_warned_and_never_overridden(self):
        self.lua(r"""
set_privacy(1);host_lobby();key(SOS_KEY,'1');key(PRIVACY_KEY,'0')
seconds(3)
assert(#calls==0 and read_key(PRIVACY_KEY)=='0')
assert(count('MATCHMAKING SAFETY WARNING: an SOS Beacon is active and the game made this lobby PUBLIC')==1)
assert(count('HD2Runtime cannot block the SOS Beacon')==1)
seconds(0.25)
assert(screens[#screens].texts[2]=='SOS Beacon active: this lobby is PUBLIC and strangers can join.')
-- It ends: the game advertises the setting again; logged once, still no call.
key(SOS_KEY,'0');key(PRIVACY_KEY,'1')
seconds(2)
assert(#calls==0 and count('the SOS Beacon ended')==1)
-- A Public setting while an SOS Beacon is active: the setting is enforced (key 19 stays 0: the game's rule).
key(SOS_KEY,'1');key(PRIVACY_KEY,'0');set_privacy(0)
seconds(1)
assert(#calls==1 and privacy()==1 and read_key(PRIVACY_KEY)=='0')
assert(count('an SOS Beacon is active')==2)
""")

    def test_a_client_lobby_cache_is_never_corrected_but_its_own_public_setting_is(self):
        self.lua(r"""
set_privacy(1);host_lobby({members={OTHER,LOCAL},host=OTHER});key(PRIVACY_KEY,'0');key(SOS_KEY,'0')
seconds(3)
assert(#calls==0)
set_privacy(0)
seconds(1)
assert(#calls==1 and count('(setting Public, advertised "0", client, lobby joined')==1)
""")

    def test_an_unproven_pin_means_no_call_and_a_loud_warning(self):
        self.lua(r"""
local pin=MS.pins[1]
W.write(W.GAME+pin.rva,'\204')
set_privacy(0);quickplay(true)
seconds(3)
assert(#calls==0 and privacy()==0 and quickplaying())
assert(count('MATCHMAKING SAFETY UNAVAILABLE (UNSUPPORTED_BUILD: game.dll+')==1)
assert(count('Public matchmaking is NOT blocked. Set Privacy to Friends Only / Invite Only and do not use Quickplay.')==1)
assert(count('MATCHMAKING SAFETY ACTIVE')==0)
local t=screens[#screens].texts
assert(t[2]=='Safety UNAVAILABLE: Public matchmaking is NOT blocked.'
    and t[3]=='Set Friends Only / Invite Only and do not use Quickplay.')
""")

    def test_no_live_process_means_no_call_and_the_watch_ends(self):
        # A snapshot or offline harness is not the live game: the watch ends itself at its first tick (no native
        # adapter, no call, no write) so the Runtime's update hook still detaches when nothing else needs it.
        self.lua(r"""
safety.set_adapter(nil)          -- the fixture's process is not live: the native adapter is never created
local watch=safety.start()
set_privacy(0);quickplay(true)
seconds(3)
assert(#calls==0 and privacy()==0)
assert(watch.status=='complete')
assert(count('cannot be changed')==0 and count('MATCHMAKING SAFETY ACTIVE')==0)
""")

    def test_api_starts_the_watch_only_inside_the_game(self):
        source = (ROOT / 'api/hd2.lua').read_text(encoding='utf-8')
        start = source.index("require('hd2runtime/runtime/matchmaking_safety').start()")
        guard = source.rfind("if type(rawget(_G,'stingray'))=='table'then", 0, start)
        self.assertGreaterEqual(guard, 0)
        self.assertLess(source.count(chr(10), guard, start), 3)

    def test_unreadable_layout_and_unloaded_descriptors_and_busy_lobbies_wait_without_a_call(self):
        self.lua(r"""
-- The settings descriptors are not loaded yet (the setter would read a NULL descriptor): waiting.
W.write(W.GAME+L.counts,W.u32(0))
set_privacy(0)
seconds(3)
assert(#calls==0 and count('MATCHMAKING SAFETY WAITING (NOT_READY')==1)
W.write(W.GAME+L.counts,W.u32(2))
-- A lobby that exists but is not joined yet (PlayfabLobby state 2): waiting.
host_lobby({state=2})
seconds(3)
assert(#calls==0 and count('MATCHMAKING SAFETY WAITING (LOBBY_BUSY')==1)
host_lobby()
seconds(1)
assert(#calls==1 and privacy()==1)
-- An unreadable matchmaker: unavailable (loud), no call.
W.write(W.GAME+MS.matchmaker.global,W.u64(0x7FFF00000000))
set_privacy(0)
seconds(3)
assert(#calls==1 and count('MATCHMAKING SAFETY UNAVAILABLE')==0)      -- a transition is given UNREADABLE_GRACE s
seconds(3)
assert(#calls==1 and count('MATCHMAKING SAFETY UNAVAILABLE (UNREADABLE: the matchmaker)')==1)
""")

    def test_an_unverified_call_stops_that_enforcement_after_three_tries(self):
        self.lua(r"""
local inert={set_privacy=function()calls[#calls+1]={what='privacy'};return true end,
    stop_quickplay=function()calls[#calls+1]={what='quickplay'};return true end}
safety.set_adapter(inert)
set_privacy(0)
seconds(10)
assert(#calls==3,#calls)
assert(count('MATCHMAKING SAFETY CALL NOT VERIFIED (privacy, 3 of 3)')==1)
assert(count('MATCHMAKING SAFETY FAILED (privacy): 3 unverified calls; this enforcement stops for the session')==1)
assert(count('cannot be changed (STOPPED')==1)
""")

    def test_calls_run_only_inside_the_runtime_update(self):
        self.lua(r"""
safety.reset_for_tests();safety.set_adapter(adapter)
set_privacy(0)
local world=assert(world_module.open())
local out=safety.check(world)
assert(out.privacy_action.status=='deferred'and out.privacy_action.code=='NOT_GAME_THREAD'and #calls==0)
assert(count('MATCHMAKING SAFETY WAITING (NOT_GAME_THREAD')==1)
""")

    def test_a_gui_error_disables_the_notice_and_the_log_keeps_every_line(self):
        self.lua(r"""
safety.hooks.open_screen=function()return {width=1920,height=1080,rect=function()error('boom')end,
    text=function()return 1 end,close=function()end}end
set_privacy(0)
seconds(1)
assert(#calls==1 and count('the on-screen notice is unavailable')==1)
set_privacy(0);seconds(2)
assert(#calls==2 and count('the on-screen notice is unavailable')==1 and safety.status().gui_disabled)
""")


if __name__ == '__main__':
    unittest.main()
