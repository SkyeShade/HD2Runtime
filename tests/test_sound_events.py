"""Playing game sound events (hd2.sounds.play / available / asset / name_for; runtime/sound_events.lua,
docs/sounds.md) against a recording fake of the Wwise plugin's Lua API: names that hash to an event id, the guards,
the per-mod rate limit, positions, stopping, and a catalogue sound's bank as an asset target."""
import unittest

from support import run

HARNESS = r'''
local logged={}
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function(line)logged[#logged+1]=line end
local events=require('hd2runtime/runtime/events')
events.reset_for_tests()
local posts,stops,known={},{},{}
local NEXT=100
rawset(_G,'stingray',{
    Wwise={wwise_world=function(w)return {world=w}end,has_event=function(name)return known[name]==true end},
    WwiseWorld={trigger_event=function(ww,name,pos)NEXT=NEXT+1;posts[#posts+1]={world=ww.world,name=name,pos=pos}
        return NEXT,7 end,stop_event=function(ww,id)stops[#stops+1]={world=ww.world,id=id}end},
    Vector3=function(x,y,z)return {x,y,z}end})
local S=require('hd2runtime/runtime/sound_events')
local U=require('hd2runtime/runtime/ui_sound')
S.reset_for_tests()
local NOW=0
S.hooks.game_world=function()return 'GAMEWORLD'end
S.hooks.playing_entry=function(counter)return {state=0,id=counter+1000}end
S.hooks.now=function()return NOW end
local hd2=require('hd2runtime/api/hd2')
'''


class SoundEventTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body), b'ok')

    def test_names_hash_to_the_ids_they_stand_for(self):
        self.lua(r'''
assert(S.mul32(0x01000193,0x359C449B)==1,'the FNV prime inverse')
for _,id in ipairs({0x6A84A787,0x98F18D8B,0x825E6711,0xDEADBEEF,1,0xFFFFFFFF})do
    local name=hd2.sounds.name_for(id)
    assert(name and name:match('^hd2runtime_[a-z0-9_]+$')and#name==18 and U.fnv1(name)==id,tostring(id))
    assert(hd2.sounds.name_for(id)==name,'cached and stable')
end
-- forward and backward are inverse steps.
local h=0x12345678
for c=0,255 do assert(S.backward(S.forward(h,c),c)==h)end
assert(not pcall(hd2.sounds.name_for,0)and not pcall(hd2.sounds.name_for,2^32))
return 'ok'
''')

    def test_every_catalogue_event_has_a_generated_name_and_the_table_is_current(self):
        import importlib.util
        from support import ROOT
        spec = importlib.util.spec_from_file_location('gen_names', ROOT / 'scripts/generate_sound_event_names.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # The id set, every name's hash and form, and a sample searched again (scripts/generate_sound_event_names.py).
        self.assertEqual(module.check(), [], 'stale: run py scripts/generate_sound_event_names.py')
        count = len(module.catalogue_ids())
        self.lua(r'''
local names=require('hd2runtime/domains/sound_event_names')
local W=require('hd2runtime/runtime/wwise_names')
local D=require('hd2runtime/domains/weapon_sounds')
local E=require('hd2runtime/domains/sound_events')
local n=0
for id,name in pairs(names)do assert(W.id(name)==id and U.fnv1(name)==id,name);n=n+1 end
assert(n==%d,'the catalogues hold %d ids: '..n)
-- Every event of the full catalogue has a name (its own Wwise name or a generated one).
for name,e in pairs(E.events)do assert(e.wwise or names[tonumber(e.id,16)],name)end
-- Every catalogue sound resolves without a search (the search is never called).
local search=W.search;W.search=function()error('searched at runtime')end
for name in pairs(D.sounds)do
    local spec=S.resolve(name)
    if spec then assert(names[spec.id]==spec.name,name)end
end
W.search=search
return 'ok'
''' % (count, count))

    def test_play_by_catalogue_name_ui_key_wwise_name_and_id(self):
        self.lua(r'''
-- Nothing is posted unless the sound engine knows the event.
local h,code,why=hd2.sounds.play('ui_generic_select',{owner='mods/t/s'})
assert(h==nil and code=='NO_EVENT'and#posts==0,tostring(code))
known.ui_generic_select=true
h=assert(hd2.sounds.play('ui_generic_select',{owner='mods/t/s'}))
assert(h.state=='playing'and h.playing==101 and posts[1].name=='ui_generic_select'and posts[1].world=='GAMEWORLD')
assert(posts[1].pos==nil,'no source argument: the world default source')
-- The ui family: the loadout screen's own events by key.
local pick=U.EVENTS.stratagem_pick
known[pick.name]=true
assert(hd2.sounds.play('ui/stratagem_pick',{owner='mods/t/s'}))
assert(posts[2].name==pick.name)
-- A catalogue loop posts its loop start through a name hashing to it; a shot its shot event.
local gatling=S.resolve('sentry/gatling')
assert(gatling.id==0x98F18D8B and U.fnv1(gatling.name)==0x98F18D8B and gatling.kind=='loop')
local mg=S.resolve('support/mg206')
assert(mg.id==0x825E6711 and mg.kind=='shot'and mg.midi)
known[gatling.name]=true
local loop=assert(hd2.sounds.play('sentry/gatling',{owner='mods/t/s',position={1,2,3}}))
assert(posts[3].name==gatling.name and posts[3].pos[1]==1 and posts[3].pos[3]==3,'a 3D post at the position')
assert(loop:stop()==true and stops[1].id==loop.playing and stops[1].world=='GAMEWORLD')
assert(loop:stop()==nil,'stopped once')
-- {id = ...}
local by_id=S.resolve({id=0x0DBB2A14})
known[by_id.name]=true
assert(hd2.sounds.play({id=0x0DBB2A14},{owner='mods/t/s'}))
assert(U.fnv1(posts[4].name)==0x0DBB2A14)
-- available() asks has_event, nothing posted.
local n=#posts
assert(hd2.sounds.available('sentry/gatling')==true and hd2.sounds.available('support/mg206')==false and#posts==n)
return 'ok'
''')

    def test_refusals_rate_limit_and_ownership(self):
        self.lua(r'''
known.boom=true
for _,bad in ipairs({'',42,string.rep('x',129),'a\nb',{id=0},{id=1.5}})do
    local h,code=hd2.sounds.play(bad,{owner='mods/t/r'});assert(h==nil and(code=='UNKNOWN_EVENT'),tostring(code))
end
local h,code=hd2.sounds.play('boom',{owner='mods/t/r',position={0/0,1,2}});assert(h==nil and code=='INVALID')
-- No engine API: refused before anything is called.
local saved=stingray.WwiseWorld;stingray.WwiseWorld=nil
h,code=hd2.sounds.play('boom',{owner='mods/t/r'});assert(code=='NO_API')
stingray.WwiseWorld=saved
-- No game world: refused.
local gw=S.hooks.game_world;S.hooks.game_world=function()return nil,'UNAVAILABLE','not readable'end
h,code=hd2.sounds.play('boom',{owner='mods/t/r'});assert(code=='UNAVAILABLE')
S.hooks.game_world=gw
-- A post the engine does not make (playing id 0).
local trig=stingray.WwiseWorld.trigger_event;stingray.WwiseWorld.trigger_event=function()return 0 end
h,code=hd2.sounds.play('boom',{owner='mods/t/r2'});assert(code=='NOT_PLAYED')
stingray.WwiseWorld.trigger_event=trig
-- Rate limit: per mod, per second.
local played=0
for _=1,40 do if hd2.sounds.play('boom',{owner='mods/t/rate'})then played=played+1 end end
assert(played==S.RATE,played)
assert(hd2.sounds.play('boom',{owner='mods/t/other'}),'another mod has its own budget')
NOW=NOW+1.5
assert(hd2.sounds.play('boom',{owner='mods/t/rate'}),'a new second')
-- The owner is the calling mod.
local handle
hd2.events.run_as('mods/t/scoped',function()handle=hd2.sounds.play('boom')end)
assert(handle and handle.owner=='mods/t/scoped')
return 'ok'
''')

    def test_a_catalogue_sound_is_an_asset_target(self):
        self.lua(r'''
local api_assets=require('hd2runtime/api/assets')
local target=hd2.sounds.asset('sentry/gatling')
assert(target.resource=='sound'and target.sound=='sentry/gatling')
local deps=assert(api_assets.sound_dependencies('sentry/gatling'))
assert(#deps>=1 and deps[1].package=='0x992D325D88DE5FBF',tostring(deps[1]and deps[1].package))
local info=hd2.asset_dependency(target)
assert(info.known and info.autoLoadSupported and info.key=='sound/sentry/gatling')
-- Resident-only sounds have no package to request: refused with the reason, never guessed.
local resident
for _,s in ipairs(hd2.sounds.list({resident_only=true}))do resident=s.name;break end
local none,why=api_assets.sound_dependencies(resident)
assert(none==nil and why:find('resident-only',1,true),tostring(why))
assert(hd2.asset_dependency(hd2.sounds.asset(resident)).known==false)
assert(not pcall(hd2.sounds.asset,'no/such/sound'))
-- The pelican's own sound needs nothing.
assert(#api_assets.sound_dependencies('pelican/chin_autocannon')==0)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
