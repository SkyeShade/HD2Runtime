"""The local Helldiver avatar Runtime's actions are credited to (runtime/handles.lua local_avatar): the player list
decides, as hd2.local_player():avatar() does, with no record limit; dead, stale and replaced avatars are never used;
the owned health records are only a fallback when the list has no local player."""
import unittest

from support import run
from test_event_scripting import PRELUDE

# Room for more than 64 health records (the fixture's default capacity).
BODY = "rawset(_G,'EVENT_FIXTURE_CAPACITY',256)\n" + PRELUDE + r'''
local function avatar()
    local world=assert(world_module.open())
    return handles.local_avatar(world)
end
local function explode()
    local action
    hd2.events.run_as('mods/t/avatar',function()
        action=hd2.explosions.spawn('R-36 Eruptor',{position={x=1,y=2,z=3}})
    end)
    return action
end
local function crowd(first,count)
    for entity=first,first+count-1 do W.add{entity=entity,type=MARAUDER,unit=0,health=125,owned=true}end
end
'''


class LocalAvatarTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(BODY + body), b'ok')

    def test_an_avatar_beyond_the_first_64_owned_records_is_found(self):
        self.lua(r'''
-- As host this machine owns nearly every entity: 80 owned enemies are created before the Helldiver lands.
crowd(1000,80)
W.players({{peer=LOCAL,avatar=900}},LOCAL)
W.add{entity=900,type=W.AVATAR,unit=7900,health=125,owned=true}
W.unit(7900,0,0,0)
W.state(4,{host=true});tick()
local world=assert(world_module.open())
local header=world_module.health_header(world,world.view.slot())
local position
for index=0,header.live-1 do
    if world_module.descriptor(world,header,index).entity==900 then position=index end
end
assert(position==80,tostring(position))
local found=assert(avatar())
assert(found.id==900 and found.route=='player_list'and found.unit==7900 and found.type==W.AVATAR)
-- The actions credited to it work.
local a=explode()
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
-- The fallback (no local player in the list) now scans every live record too.
W.players({},LOCAL)
found=assert(avatar())
assert(found.id==900 and found.route=='owned_records')
return 'ok'
''')

    def test_death_and_reinforcement_never_use_the_old_avatar(self):
        self.lua(r'''
mission({host=true})
assert(avatar().id==100)
-- Downed still acts; dead does not, even while the player list still names it.
W.set(100,{life=1});tick()
assert(avatar().id==100)
-- Death: the local player's death is reported while the list still names the dead avatar. The current avatar is gone
-- (strict), but a reaction to the death is still credited to the avatar that died (the action layer's include_dead).
local reacted
hd2.events.run_as('mods/t/avatar',function()
    hd2.events.on('player_died',function(event)if event.local_player then reacted=explode()end end)
end)
tick(2)
W.set(100,{life=2,health=0});tick(2)
local none,why=avatar()
assert(none==nil and why:find('entity 100 is dead',1,true),tostring(why))
assert(reacted and reacted.status=='requested',tostring(reacted and reacted.code)..' '..tostring(reacted and reacted.reason))
local world=assert(world_module.open())
local dying=assert(handles.local_avatar(world,{include_dead=true}))
assert(dying.id==100 and dying.dead==true and dying.route=='player_list')
assert(W.runtime.explosions[#W.runtime.explosions].source==100)
-- Waiting to respawn: no avatar in the list means none, not the dead record the health manager still holds.
W.players({{peer=LOCAL,lifecycle=2}},LOCAL);tick()
none,why=avatar()
assert(none==nil and why=='the local player has no avatar now',tostring(why))
assert(handles.local_avatar(world,{include_dead=true})==nil,'never an avatar the list no longer names')
local a=explode()
assert(a.code=='NO_LOCAL_AVATAR'and a.reason:find('no avatar now',1,true),tostring(a.code)..' '..tostring(a.reason))
-- Reinforcement: a new entity, created after the dead one, is the avatar at once.
W.players({{peer=LOCAL,avatar=101}},LOCAL)
W.add{entity=101,type=W.AVATAR,unit=7101,health=125,owned=true}
W.unit(7101,5,5,0);tick()
local found=assert(avatar())
assert(found.id==101 and found.route=='player_list')
assert(explode().status=='requested')
-- The fallback skips the dead avatar record that comes first, even when dead avatars are accepted.
W.players({},LOCAL)
found=assert(avatar())
assert(found.id==101 and found.route=='owned_records')
assert(handles.local_avatar(world,{include_dead=true}).id==101)
-- The dead avatar replaced by its corpse; then the list naming a destroyed entity (stale generation).
W.replace_by_corpse(100,850)
W.players({{peer=LOCAL,avatar=101}},LOCAL);tick()
assert(avatar().id==101)
W.remove(101)
none,why=avatar()
assert(none==nil and why:find('no longer exists',1,true),tostring(why))
return 'ok'
''')

    def test_mission_transitions_follow_the_current_avatar(self):
        self.lua(r'''
mission({host=true})
assert(avatar().id==100 and explode().status=='requested')
-- The mission ends: the avatar leaves the player list; actions stop at the game state first.
W.players({{peer=LOCAL}},LOCAL)
W.state(3);tick()
local none,why=avatar()
assert(none==nil and why=='the local player has no avatar now',tostring(why))
assert(explode().code=='NOT_IN_MISSION')
-- Aboard the ship the local player has its ship avatar.
W.players({{peer=LOCAL,avatar=300}},LOCAL)
W.add{entity=300,type=W.AVATAR,unit=7300,health=125,owned=true}
W.unit(7300,0,0,0);tick()
assert(avatar().id==300)
-- The next mission: a new avatar, while the ship avatar's record still exists (and comes first).
W.players({{peer=LOCAL,avatar=400}},LOCAL)
W.add{entity=400,type=W.AVATAR,unit=7400,health=125,owned=true}
W.unit(7400,0,0,0)
W.state(4,{host=true});tick()
local found=assert(avatar())
assert(found.id==400 and found.route=='player_list')
assert(explode().status=='requested')
-- Without a local player, two owned living avatars are ambiguous: refused, never guessed.
W.players({},LOCAL)
none,why=avatar()
assert(none==nil and why=='more than one owned, living Helldiver avatar',tostring(why))
return 'ok'
''')

    def test_another_players_avatar_is_never_the_local_one(self):
        self.lua(r'''
-- A client's avatar is not owned here; the local player's is. The list decides by the local peer.
W.players({{peer=OTHER,avatar=200},{peer=LOCAL,avatar=100}},LOCAL)
W.add{entity=200,type=W.AVATAR,unit=7200,health=125,owned=false}
W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
W.unit(7200,0,0,0);W.unit(7100,0,0,0)
W.state(4,{host=true});tick()
assert(avatar().id==100)
-- A local avatar this machine does not own is refused rather than acted for.
W.players({{peer=LOCAL,avatar=200}},LOCAL);tick()
local none,why=avatar()
assert(none==nil and why:find('not owned by this machine',1,true),tostring(why))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
