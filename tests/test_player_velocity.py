"""hd2.actions.add_velocity: the game's own MotionComponent velocity setter (SetVelocity) on the local player's avatar
(research/player-avatar-actions-F5FEE03DCFDB.json). Offline: the injury test world plus a motion manager laid out as
the research found it, SetVelocity's entry bytes and a fake native call that records what Runtime passes."""
import json
import unittest

from support import ROOT, run
import test_player_injury as injury_tests

RESEARCH = ROOT / 'research/player-avatar-actions-F5FEE03DCFDB.json'

PRELUDE = injury_tests.PRELUDE + r'''
local MV=natives.velocity
W.write(W.GAME+MV.rva,unhex(MV.prologue))
-- The motion manager: entity hash, descriptors, records (velocity at +0); index 2 for the avatar.
local motion=W.alloc(0x5000)
W.write(W.GAME+MV.manager,W.u64(motion))
local buckets=W.alloc(64*8)
for slot=0,63 do W.write(buckets+slot*8,W.u32(0)..W.u32(0))end
W.write(motion+MV.capacity,W.u32(16))
W.write(motion+MV.hash,W.u64(buckets)..W.u32(64)..W.u32(0)..W.u32(1))
local descriptors=W.alloc(16*8)
W.write(motion+MV.descriptors,W.u64(descriptors))
local records=W.alloc(16*MV.stride)
W.write(motion+MV.records,W.u64(records))
local function give_motion(entity,index,owned,vx,vy,vz)
    W.write(buckets+(entity%64)*8,W.u32(entity)..W.u32(index))
    local d=W.alloc(0x18)
    W.write(d,W.u32(0)..W.u32(0)..W.u32(entity)..W.u32(0)..W.u32(0x7FFF)..W.u32(owned and 1 or 0))
    W.write(descriptors+index*8,W.u64(d))
    W.write(records+index*MV.stride,W.f32(vx or 0)..W.f32(vy or 0)..W.f32(vz or 0))
end
W.runtime.velocities={}
function W.runtime.native_set_velocity(entry,entity,x,y,z)
    assert(entry==W.GAME+MV.rva,'the velocity was set through the wrong function')
    W.runtime.velocities[#W.runtime.velocities+1]={entity=entity,x=x,y=y,z=z}
    W.write(records+2*MV.stride,W.f32(x)..W.f32(y)..W.f32(z))
    return true
end
local function kick(player,v,opts)
    return in_update(function()
        local action
        hd2.events.run_as('mods/t/kick',function()action=hd2.actions.add_velocity(player,v,opts)end)
        return action
    end)
end
local function near(a,b)return math.abs(a-b)<1e-4 end
'''


class PlayerVelocityTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_the_research_names_the_setter_and_the_avatar_motion_record(self):
        research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual(research['setVelocity']['rva'], 0x4A7550)
        self.assertEqual(research['setVelocity']['gameLaunch'], {'horizontal': 5.8, 'up': 3.3})
        for item in research['observations']:
            if item['localAvatar']:
                motion = item['localAvatar']['motion']
                self.assertTrue(motion['descriptorNamesAvatar'] and motion['owned'], item['snapshot'])

    def test_the_change_is_added_to_the_current_velocity_through_the_game_setter(self):
        self.lua(r'''
mission({host=true})
give_motion(100,2,true,1,2,0)
local me=hd2.local_player()
local a=kick(me,{x=0,y=3,z=6})
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
local call=W.runtime.velocities[1]
assert(call.entity==100 and near(call.x,1)and near(call.y,5)and near(call.z,6),('%s %s %s'):format(call.x,call.y,call.z))
assert(near(a.after.z,6)and near(a.velocity.y,3)and a.owner=='mods/t/kick')
local m=in_update(function()return me:add_velocity({x=1,y=0,z=0},{owner='mods/t/method'})end)
assert(m.status=='requested'and m.owner=='mods/t/method'and near(W.runtime.velocities[2].x,2))
assert(count('velocity (0.00, 3.00, 6.00) added to the local avatar 100')==1)
assert(hd2.actions.status().add_velocity.status=='available')
return 'ok'
''')

    def test_invalid_changes_and_too_fast_results_are_refused(self):
        self.lua(r'''
mission({host=true})
give_motion(100,2,true,0,0,0)
local me=hd2.local_player()
for _,v in ipairs({{x=0,y=0,z=26},{x=20,y=20,z=0},{x=0/0,y=0,z=0},{x=math.huge,y=0,z=0},{x=1,y=2},{x='1',y=0,z=0},
        {x=0,y=0,z=0},5,'up'})do
    local a=kick(me,v)
    assert(a.code=='INVALID_VELOCITY',tostring(a.code))
end
assert(kick(nil,{x=0,y=0,z=1}).code=='INVALID_TARGET')
assert(kick(me,{x=0,y=0,z=1},{impulse=true}).code=='INVALID_OPTION')
give_motion(100,2,true,0,0,40)                         -- already fast: the result would pass 50 m/s
assert(kick(me,{x=0,y=0,z=20}).code=='TOO_FAST')
assert(#W.runtime.velocities==0)
return 'ok'
''')

    def test_remote_unowned_downed_and_out_of_mission_avatars_are_refused(self):
        self.lua(r'''
mission({host=false})                                  -- a client moves its own avatar
local me=hd2.local_player()
local other
for _,p in ipairs(hd2.players())do if not p:is_local_player()then other=p end end
assert(kick(other,{x=0,y=0,z=1}).code=='NOT_LOCAL_PLAYER')
assert(kick(me,{x=0,y=0,z=1}).code=='VELOCITY_UNAVAILABLE','no motion record')
give_motion(100,2,false,0,0,0)
assert(kick(me,{x=0,y=0,z=1}).code=='NOT_LOCAL_PLAYER','the motion record is not owned here')
give_motion(100,2,true,0,0,0)
assert(kick(me,{x=0,y=0,z=1}).status=='requested')
W.set(100,{life=1});tick()
assert(kick(me,{x=0,y=0,z=1}).code=='AVATAR_DOWNED')
W.set(100,{life=0});W.state(3);tick()
assert(kick(me,{x=0,y=0,z=1}).code=='NOT_IN_MISSION')
assert(#W.runtime.velocities==1)
return 'ok'
''')

    def test_a_changed_or_missing_native_path_refuses_and_changes_are_rate_limited(self):
        self.lua(r'''
hd2.events.run_as('mods/t/kick',function()hd2.events.on('mission_started',function()end)end)
mission({host=true})
give_motion(100,2,true,0,0,0)
local me=hd2.local_player()
local outside
hd2.events.run_as('mods/t/kick',function()outside=hd2.actions.add_velocity(me,{x=0,y=0,z=1})end)
assert(outside.code=='NOT_GAME_THREAD',tostring(outside.code))
W.write(W.GAME+MV.rva,string.char(0xCC))
assert(kick(me,{x=0,y=0,z=1}).code=='VELOCITY_UNAVAILABLE')
W.write(W.GAME+MV.rva,unhex(MV.prologue))
local saved=W.runtime.native_set_velocity
W.runtime.native_set_velocity=nil
assert(kick(me,{x=0,y=0,z=1}).code=='VELOCITY_UNAVAILABLE')
W.runtime.native_set_velocity=saved
assert(#W.runtime.velocities==0)
tick(24)
local codes=in_update(function()
    local out={}
    hd2.events.run_as('mods/t/kick',function()
        for _=1,actions.VELOCITY_BURST+1 do out[#out+1]=hd2.actions.add_velocity(me,{x=0,y=0,z=1}).code or'ok'end
    end)
    return out
end)
assert(codes[actions.VELOCITY_BURST]=='ok'and codes[actions.VELOCITY_BURST+1]=='RATE_LIMITED',table.concat(codes,','))
tick(8)
assert(kick(me,{x=0,y=0,z=1}).status=='requested','refilled')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
