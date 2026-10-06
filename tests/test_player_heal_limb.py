"""hd2.actions.heal_limb / heal_limbs: the game's own one-zone restore (RestoreZone) on the local player's avatar
(research/player-avatar-actions-F5FEE03DCFDB.json). Offline: the injury test world plus RestoreZone's entry bytes and a
fake native call that records what Runtime passes and restores the fixture zone the way the game does."""
import json
import unittest

from support import ROOT, run
import test_player_injury as injury_tests

RESEARCH = ROOT / 'research/player-avatar-actions-F5FEE03DCFDB.json'

PRELUDE = injury_tests.PRELUDE + r'''
local LH=natives.limbHeal
W.write(W.GAME+LH.rva,unhex(LH.prologue))
local ZONE_OF={}
for name,zone in pairs(LH.zones)do ZONE_OF[zone]=name end
-- The avatar's health record address now (the fixture relays records when entities come and go).
local function record_of(entity)
    local world=assert(world_module.open())
    local state=assert(world_module.entity_state(world,entity))
    return state.header.records+state.index*natives.health.stride
end
local function limb(name)for _,l in ipairs(IJ.limbs)do if l.name==name then return l end end end
-- Sets a limb zone's health and state (2 = injured) in the avatar's record.
local function set_zone(entity,name,health,state)
    local l=limb(name)
    local record=record_of(entity)
    W.write(record+IJ.zoneHealth+4*l.zoneIndex,W.u32(health%4294967296))
    local states=W.read(record+IJ.zoneStates,4):byte(1)+W.read(record+IJ.zoneStates,4):byte(2)*256
    local shift=2^(2*l.zoneIndex)
    states=states-(math.floor(states/shift)%4)*shift+(state or 0)*shift
    W.write(record+IJ.zoneStates,W.u32(states))
end
local function zone_health(entity,name)
    local raw=W.read(record_of(entity)+IJ.zoneHealth+4*limb(name).zoneIndex,4)
    local n=raw:byte(1)+raw:byte(2)*256+raw:byte(3)*65536+raw:byte(4)*16777216
    return n>=2147483648 and n-4294967296 or n
end
W.runtime.restores={}
function W.runtime.native_restore_zone(entry,entity,zone)
    assert(entry==W.GAME+LH.rva,'a zone was restored through the wrong function')
    local name
    for _,l in ipairs(IJ.limbs)do if LH.zones[l.name]==zone then name=l.name end end
    assert(name,'a zone name the avatar does not have')
    W.runtime.restores[#W.runtime.restores+1]={entity=entity,zone=zone,limb=name}
    set_zone(entity,name,limb(name).maxDamage,0)          -- the game: full health, state cleared
    return true
end
local function heal(player,name,amount,opts)
    return in_update(function()
        local action
        hd2.events.run_as('mods/t/limbs',function()action=hd2.actions.heal_limb(player,name,amount,opts)end)
        return action
    end)
end
'''


class PlayerHealLimbTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_the_research_restores_one_zone_and_names_every_limb_zone(self):
        research = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual(research['writes'], 0)
        self.assertFalse(any(research['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(research['restoreZone']['rva'], 0x65B2D0)
        self.assertEqual(research['restoreZone']['limbZones'], {'head': 'head', 'chest': 'body', 'l_hand': 'arm_left',
            'r_hand': 'arm_right', 'l_knee': 'leg_left', 'r_knee': 'leg_right'})
        for item in research['observations']:
            if item['localAvatar']:
                self.assertTrue(all(item['localAvatar']['zoneNames'].values()), item['snapshot'])

    def test_every_limb_is_restored_through_its_own_zone_name(self):
        self.lua(r'''
actions.LIMB_HEAL_BURST=100                            -- this test is not about the rate limit
mission({host=true})
local me=hd2.local_player()
for index,l in ipairs(IJ.limbs)do
    set_zone(100,l.name,0,2)                             -- injured
    local a=heal(me,l.name)
    assert(a.status=='requested',l.name..' '..tostring(a.code)..' '..tostring(a.reason))
    local call=W.runtime.restores[index]
    assert(call.entity==100 and call.zone==LH.zones[l.name]and call.limb==l.name,l.name)
    assert(a.zone_health==0 and a.injured_before==true and a.zone==l.zone,l.name)
    assert(zone_health(100,l.name)==l.maxDamage,l.name)
    assert(a:describe().limb==l.name and a.owner=='mods/t/limbs')
end
assert(count('limb heal r_hand (arm_right) requested on the local avatar 100 by mods/t/limbs')==1)
-- 'full' and an amount that covers what is missing are the same restore; less is refused (no partial heal exists).
set_zone(100,'r_hand',20,0)
assert(heal(me,'r_hand','full').status=='requested')
set_zone(100,'r_hand',20,0)
local partial=heal(me,'r_hand',10)
assert(partial.code=='PARTIAL_UNSUPPORTED'and partial.reason:find('missing 15'),tostring(partial.reason))
assert(heal(me,'r_hand',15).status=='requested'and zone_health(100,'r_hand')==35)
-- heal_limbs: every limb, one request; player methods are the same actions.
for _,l in ipairs(IJ.limbs)do set_zone(100,l.name,0,2)end
local all=in_update(function()
    local a
    hd2.events.run_as('mods/t/limbs',function()a=me:heal_limbs()end)
    return a
end)
assert(all.status=='requested'and#all.healed==6 and all.owner=='mods/t/limbs',tostring(all.code))
for _,l in ipairs(IJ.limbs)do assert(zone_health(100,l.name)==l.maxDamage,l.name)end
local m=in_update(function()return me:heal_limb('l_knee','full',{owner='mods/t/method'})end)
assert(m.status=='requested'and m.owner=='mods/t/method')
assert(hd2.actions.status().heal_limb.status=='available')
return 'ok'
''')

    def test_invalid_limbs_amounts_and_targets_are_refused_before_any_game_call(self):
        self.lua(r'''
mission({host=true})
local me=hd2.local_player()
for _,name in ipairs({'r_arm','arm_right','R_HAND','',5})do assert(heal(me,name).code=='UNKNOWN_LIMB',tostring(name))end
assert(heal(me,nil).code=='UNKNOWN_LIMB')
for _,amount in ipairs({0,-1,1.5,36,'half',0/0,math.huge,{}})do
    assert(heal(me,'r_hand',amount).code=='INVALID_AMOUNT',tostring(amount))
end
assert(heal(me,'r_hand','full',{buildup=1}).code=='INVALID_OPTION')
assert(heal(nil,'r_hand').code=='INVALID_TARGET')
assert(#W.runtime.restores==0)
return 'ok'
''')

    def test_remote_players_outside_a_mission_and_downed_avatars_are_refused(self):
        self.lua(r'''
mission({host=false})                                  -- a client heals its own avatar
local other
for _,p in ipairs(hd2.players())do if not p:is_local_player()then other=p end end
assert(heal(other,'r_hand').code=='NOT_LOCAL_PLAYER')
assert(heal(hd2.local_player(),'r_hand').status=='requested')
W.set(100,{life=1});tick()
assert(heal(hd2.local_player(),'r_hand').code=='AVATAR_DOWNED')
W.set(100,{life=2});tick()
assert(heal(hd2.local_player(),'r_hand').code=='NO_LOCAL_AVATAR')
W.set(100,{life=0});W.state(3);tick()
assert(heal(hd2.local_player(),'r_hand').code=='NOT_IN_MISSION')
assert(#W.runtime.restores==1)
return 'ok'
''')

    def test_a_changed_or_missing_native_path_refuses_and_requests_are_rate_limited(self):
        self.lua(r'''
hd2.events.run_as('mods/t/limbs',function()hd2.events.on('mission_started',function()end)end)
mission({host=true})
local me=hd2.local_player()
local outside
hd2.events.run_as('mods/t/limbs',function()outside=hd2.actions.heal_limb(me,'r_hand')end)
assert(outside.code=='NOT_GAME_THREAD',tostring(outside.code))
W.write(W.GAME+LH.rva,string.char(0xCC))
assert(heal(me,'r_hand').code=='LIMB_HEAL_UNAVAILABLE')
W.write(W.GAME+LH.rva,unhex(LH.prologue))
local saved=W.runtime.native_restore_zone
W.runtime.native_restore_zone=nil
assert(heal(me,'r_hand').code=='LIMB_HEAL_UNAVAILABLE')
W.runtime.native_restore_zone=saved
assert(#W.runtime.restores==0)
tick(24)                                               -- the refusals above took tokens; refill
local codes=in_update(function()
    local out={}
    hd2.events.run_as('mods/t/limbs',function()
        for _=1,actions.LIMB_HEAL_BURST+1 do out[#out+1]=hd2.actions.heal_limb(me,'r_hand').code or'ok'end
    end)
    return out
end)
assert(codes[actions.LIMB_HEAL_BURST]=='ok'and codes[actions.LIMB_HEAL_BURST+1]=='RATE_LIMITED',table.concat(codes,','))
tick(8)
assert(heal(me,'r_hand').status=='requested','refilled')
local chained
hd2.events.run_as('mods/t/chain',function()
    hd2.events.on('entity_died',function()chained=hd2.actions.heal_limb(me,'r_hand')end)
end)
events.queue('entity_died',{cause={source='mod',mod='mods/t/other',action='x#1',depth=events.MAX_CAUSE_DEPTH}})
tick()
assert(chained and chained.code=='CAUSE_DEPTH',tostring(chained and chained.code))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
