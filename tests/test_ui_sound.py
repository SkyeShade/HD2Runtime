"""Native UI sounds through the engine's Wwise Lua API (development; docs/custom-stratagems.md, "The selection sound";
runtime/ui_sound.lua; research uiSound): the event ids the loadout screen posts, posted by names whose FNV-1 hash is
that id, on the WwiseWorld of the game's own Game World, matched by its address. Offline: the event world with the
game's world context, and a recording stand-in for stingray.Application.worlds, Wwise and WwiseWorld."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

SOUND = r"""
local sound=require('hd2runtime/runtime/ui_sound')
local U=SEL.uiSound
-- The game's world context (the object the game state is read from too): its Game World and that world's WwiseWorld.
local function u64_at(at)local s=W.read(at,8);local lo,hi=0,0
    for i=4,1,-1 do lo=lo*256+s:byte(i);hi=hi*256+s:byte(i+4)end;return lo+hi*4294967296 end
local context=u64_at(W.GAME+U.context)
if context==0 then context=W.alloc(0x2000);W.write(W.GAME+U.context,W.u64(context))end
local GAME_WORLD,UI_WORLD=0x24A96260080,0x24A97280080
W.write(context+U.world,W.u32(GAME_WORLD%4294967296)..W.u32(math.floor(GAME_WORLD/4294967296)))
W.write(context+U.wwiseWorld,W.u64(0x7700))
-- The engine's world array (Application.worlds' order) and the world values Lua sees (full userdata, matched by
-- position, never by address).
W.engine_worlds({GAME_WORLD,UI_WORLD})
local GW,UW=newproxy(),newproxy()
local posts,known={},{hd2runtime_bci6lee=true,hd2runtime_bgj4s6o=true,ui_generic_select=true,hd2runtime_u64dawv=true}
local result=4242
engine.Application.worlds=function()return {GW,UW}end
engine.Wwise={wwise_world=function(w)return {wwise_of=w}end,has_event=function(name)return known[name]==true end}
engine.WwiseWorld={trigger_event=function(ww,name)posts[#posts+1]={world=ww.wwise_of,name=name};return result,1 end}
"""


def lua(body):
    return run(WORLD + SELECT + SOUND + body)


class UiSoundTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_names_hash_to_the_native_event_ids(self):
        self.check(r"""
assert(sound.fnv1('hd2runtime_bci6lee')==0x0DBB2A14 and U.events.picker_close.id==0x0DBB2A14)
assert(sound.fnv1('hd2runtime_bgj4s6o')==0x3C38FC71 and U.events.slot_select.id==0x3C38FC71)
-- The pick sound the card list posts for every pick: key 0xBE9303B7, remapped to event 0x6A84A787.
assert(sound.fnv1('hd2runtime_u64dawv')==0x6A84A787 and U.events.stratagem_pick.id==0x6A84A787
    and U.events.stratagem_pick.key==0xBE9303B7)
assert(sound.fnv1('ui_generic_select')==0x808389B8,'a real event name')
assert(sound.fnv1('UI_Generic_Select')==0x808389B8,'upper-case letters fold as Wwise folds them')
return 'ok'
""")

    def test_an_event_is_posted_on_the_game_worlds_wwise_world_only(self):
        self.check(r"""
local played=assert(sound.play('picker_close'))
assert(played.status=='played'and played.playing==4242 and#posts==1)
assert(posts[1].world==GW and posts[1].name=='hd2runtime_bci6lee','the Game World, the exact event')
assert(count('ui sound PLAYED picker_close')==1)
assert(sound.play('generic_select').status=='played'and posts[2].name=='ui_generic_select')
assert(#W.runtime.writes==0,'nothing written')
return 'ok'
""")

    def test_a_runtime_selection_plays_the_pick_sound_and_filling_the_loadout_closes_as_back_does(self):
        self.check(r"""
local slot_focus=require('hd2runtime/runtime/stratagem_slot_focus')
local real=W.runtime.native_selector_close
W.runtime.native_selector_close=function(entry,ui)posts[#posts+1]={name='CLOSE'};return real(entry,ui)end
local function names(from)local t={};for k=from+1,#posts do t[#t+1]=posts[k].name end;return table.concat(t,' ')end
-- [Big] [Eagle] [Gas Strike] [empty], the selector on slot 3: the pick sound, then (no empty slot left) the picker-close
-- sound and the close, in the native order (the card list's pick sound, then Back's sound and call).
SCREEN=W.loadout_screen({entries={{type=136},{type=22},{type=41}},editedSlot=3})
local job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=slot_focus.advance,sound=true}))
assert(job.status=='selected'and job.sound.status=='played'and job.advance.status=='closed'and job.advance.verified,
    tostring(job.advance and job.advance.reason)..' | '..table.concat(logged,' | '))
assert(names(0)=='hd2runtime_u64dawv hd2runtime_bci6lee CLOSE',names(0))
assert(posts[1].world==GW and posts[2].world==GW,'on the Game World\'s WwiseWorld')
assert(count('ui sound PLAYED stratagem_pick: a stratagem picked (a card accepted in the stratagem grid) '
    ..'(hd2runtime_u64dawv, event id 0x6A84A787)')==1,table.concat(logged,' | '))
assert(count('SELECTOR CLOSE VERIFIED')==1 and count('picker-close sound played')==1)
-- An empty slot left: the pick sound only, and the selector moves on (no close).
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=1})
local n=#posts
job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=slot_focus.advance,sound=true}))
assert(job.status=='selected'and job.advance.status=='advanced'and names(n)=='hd2runtime_u64dawv',names(n))
-- Without opts.sound no sound is posted.
n=#posts
job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=slot_focus.advance}))
assert(job.status=='selected'and job.sound==nil and names(n)=='',names(n))
return 'ok'
""")

    def test_every_refusal_calls_nothing(self):
        self.check(r"""
local function refused(code,setup,key)
    local before=#posts
    if setup then setup()end
    local r,c=sound.play(key or'picker_close')
    assert(r==nil and c==code,code..' expected, got '..tostring(c))
    assert(#posts==before,code..' posted')
end
refused('UNKNOWN_EVENT',nil,'no_such_event')
refused('NO_EVENT',nil,'item_hover_select')
engine.Application.worlds=function()return {UW}end
refused('NO_WORLD')
engine.Application.worlds=function()return {GW,UW}end
W.engine_worlds({UI_WORLD,0x1234560})
refused('NO_WORLD')
W.engine_worlds({GAME_WORLD,UI_WORLD})
W.write(context+U.wwiseWorld,W.u64(0))
refused('NO_WORLD')
W.write(context+U.wwiseWorld,W.u64(0x7700))
local saved=engine.WwiseWorld
engine.WwiseWorld=nil
refused('NO_API')
engine.WwiseWorld=saved
-- The engine posted nothing (playing id 0): reported, the one call made.
result=0
local before=#posts
local r,c=sound.play('picker_close')
assert(r==nil and c=='NOT_PLAYED'and#posts==before+1)
result=4242
mission({host=true});tick(2)
refused('IN_MISSION')
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
