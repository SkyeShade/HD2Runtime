"""Custom stratagems with several players (EXPERIMENTAL; runtime/multiplayer.lua, runtime/custom_multiplayer.lua,
runtime/carrier_allocator.lua "the lobby"; docs/custom-stratagem-api.md "Several players"):
  * the allocator: one carrier per custom id whoever selects it and in whichever slot (2 and 4 players, other slot
    numbers), distinct carriers for distinct ids, one sentry carrier for duplicate HMG Sentries;
  * the scope: only a custom stratagem call's own writes (and the entities associated with a call the orchestrator
    marked) lift the solo guard; a forged call table does not; every other guard stays;
  * the native set from the records as FIRST seen (a converted carrier a faster peer synced is never a native pick);
    a peer's token turned into a carrier this machine maps is that player's pick, reconstructed; any other type a
    DESYNC; a remote carrier beacon's thrower is the one peer whose record holds the carrier;
  * the mission start: a client refuses its own custom calls (every write is host-only) and observes others'; the host
    runs its own with several players; announced once; each call its own state, marked for the scope."""
import unittest

from support import run
from test_custom_stratagem_lobby import LOBBY, RECORDS
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_custom_payloads import examples_lua


class AllocatorTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(LOBBY + body), b'ok')

    def test_four_players_all_selecting_gas_barrage_use_one_carrier(self):
        self.lua(r'''
CANDIDATES=full()
local sel={}
for k=1,4 do sel[k]={player='P'..k,ids={'orbital_gas_barrage'}}end
local a=lobby(sel,{},4)
local c=carriers(a)
for k=1,4 do assert(c['P'..k].orbital_gas_barrage=='Orbital Gatling Barrage','P'..k)end
local gas=0
for _,id in pairs(a.reservations)do if id=='orbital_gas_barrage'then gas=gas+1 end end
assert(gas==1,'one reservation for the id')
local reused=0
for _,row in ipairs(a.mapping)do if row.slots[1].reused then reused=reused+1 end end
assert(reused==3)
return 'ok'
''')

    def test_one_custom_id_in_different_slot_numbers_uses_one_carrier(self):
        self.lua(r'''
CANDIDATES=full()
-- P2 selects it twice (slots 3 and 2, given out of order); P1 once in slot 0.
local a=lobby({{player='P2',slots={{slot=3,id='orbital_gas_barrage'},{slot=2,id='orbital_gas_barrage'}}},
    {player='P1',slots={{slot=0,id='orbital_gas_barrage'}}}},{},2)
local p1,p2=a.mapping[1],a.mapping[2]
assert(p1.player=='P1'and p2.player=='P2')
assert(p1.slots[1].slot==0 and p2.slots[1].slot==2 and p2.slots[2].slot==3)
local carrier=p1.slots[1].carrier
assert(carrier=='Orbital Gatling Barrage'and p2.slots[1].carrier==carrier and p2.slots[2].carrier==carrier)
assert(p1.slots[1].reused==false and p2.slots[1].reused and p2.slots[2].reused)
return 'ok'
''')

    def test_gas_barrage_and_pelican_take_distinct_orbital_carriers(self):
        self.lua(r'''
CANDIDATES=full()
local a=lobby({{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'pelican_close_air_support'}}},{},2)
local g,p=a.assignments.orbital_gas_barrage,a.assignments.pelican_close_air_support
assert(g.family=='orbital'and p.family=='orbital'and g.stable_id~=p.stable_id,g.carrier..' / '..p.carrier)
assert(a.reservations[g.stable_id]=='orbital_gas_barrage'and a.reservations[p.stable_id]=='pelican_close_air_support')
return 'ok'
''')

    def test_duplicate_hmg_sentries_share_one_sentry_carrier(self):
        self.lua(r'''
CANDIDATES=full()
local a=lobby({{player='P1',slots={{slot=0,id='hmg_sentry'},{slot=1,id='hmg_sentry'}}},{player='P2',ids={'hmg_sentry'}},
    {player='P3',ids={'hmg_sentry'}}},{},3)
local s=a.assignments.hmg_sentry
assert(s.family=='sentry'and s.carrier=='A/MG-43 Machine Gun Sentry')
for _,row in ipairs(a.mapping)do for _,x in ipairs(row.slots)do assert(x.carrier==s.carrier,row.player)end end
return 'ok'
''')


SCOPE = WORLD + SLOT + RECORDS + r"""
local mp=require('hd2runtime/runtime/multiplayer')
local cmp=require('hd2runtime/runtime/custom_multiplayer')
local instances=require('hd2runtime/runtime/spawned_instances')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
mp.reset_for_tests();cmp.reset_for_tests();instances.reset_for_tests()
"""


class ScopeTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(SCOPE + body), b'ok')

    def test_only_a_marked_custom_call_lifts_the_solo_guard(self):
        self.lua(r'''
local h=world_with()
local world=world_module.open()
-- The guard itself.
assert(mp.solo_guard(1,false)==nil and mp.solo_guard(2,true)==nil)
local code,why=mp.solo_guard(2,false,'why')
assert(code=='NOT_SOLO'and why:find('solo only: 2 stratagem records (why)',1,true),tostring(why))
assert(mp.allows({multiplayer=true})and not mp.allows({})and not mp.allows(nil))
-- Per entity: a call the orchestrator marked; a forged table (a call_id and multiplayer = true) is not one.
W.add{entity=5001,type='37CDE43876BA26BB',unit=0,health=1}
W.add{entity=5002,type='37CDE43876BA26BB',unit=0,health=1}
W.add{entity=5003,type='37CDE43876BA26BB',unit=0,health=1}
local real={definition='x',call_id='x#1',player='P'}
mp.mark_call(real)
assert(instances.associate(5001,real,'sentry'))
assert(instances.associate(5002,{definition='x',call_id='x#2',player='P',multiplayer=true},'sentry'))
assert(mp.entity_allowed(5001)and not mp.entity_allowed(5002)and not mp.entity_allowed(9999))
-- A child inherits its parent's scope.
assert(instances.associate_child(5001,5003,'turret')and mp.entity_allowed(5003))
-- A record write with another player's record: refused without the scope; with it the solo guard passes (no write
-- happens here: the duplicate conversion's next guard decides) and the other record is never touched.
local records=two_records(h,{136,118})
W.guarded_runtime()
local other_before=W.read(records+R.stride,R.stride)
local without=settle_job(slots.convert({token='Orbital Precision Strike',carrier='Orbital 120mm HE Barrage'}))
assert(without.code=='NOT_SOLO'and without.reason:find('only a custom stratagem call',1,true),tostring(without.reason))
local with=settle_job(slots.convert({token='Orbital Precision Strike',carrier='Orbital 120mm HE Barrage',multiplayer=true}))
assert(with.code~='NOT_SOLO',tostring(with.code)..' '..tostring(with.reason))
assert(W.read(records+R.stride,R.stride)==other_before,'another player\'s record was written')
return 'ok'
''')

    def test_first_seen_records_reconstruction_and_desync(self):
        self.lua(r'''
local h=world_with()
local world=world_module.open()
-- The peer's record: the 120mm (native), the token twice (custom or native: not distinguishable).
local records=two_records(h,{136,118,118})
local other=records+R.stride
local PEER='0000000299990000'
cmp.first_seen(world)
-- Its Runtime converts its entry 1 to the carrier (the 380mm, type 125) and the game syncs the record.
W.write(other+R.state+R.entries+1*R.entryStride,W.u32(125))
-- The native set is the first sight: the converted carrier is never a native pick.
local native=cmp.native(world,{},118)
assert(native.present[loadout.id_of(world,136)],'the native 120mm')
assert(#native.changed==0 and#native.converted==1 and native.converted[1]:find('peer '..PEER..' entry 1',1,true),
    table.concat(native.converted,'|'))
for id in pairs(native.present)do assert(loadout.type_of(world,id)~=125,'the converted carrier counted as native')end
local carriers={[125]='orbital_gas_barrage'}
local got=cmp.records_step(world,118,carriers)
assert(got[PEER]and got[PEER][1]=='orbital_gas_barrage')
assert(count('CUSTOM MP PICKS: peer '..PEER..' record entry 1')==1 and count('that player\'s orbital_gas_barrage '
    ..'(reconstructed from its synced record')==1,table.concat(logged,' | '))
cmp.records_step(world,118,carriers)
assert(count('CUSTOM MP PICKS: peer '..PEER..' record entry 1')==1,'reported once')
-- Its other token turned into a type this machine maps to no custom stratagem: a DESYNC.
W.write(other+R.state+R.entries+2*R.entryStride,W.u32(109))
cmp.records_step(world,118,carriers)
assert(count('CUSTOM MP DESYNC: peer '..PEER..' converted record entry 2')==1
    and count('this machine: orbital_gas_barrage = ')==1,table.concat(logged,' | '))
-- A remote beacon of the carrier: its thrower is the one peer whose record holds it.
local r=cmp.remote_beacon(world,{entity=7777,type=125},carriers)
assert(r.id=='orbital_gas_barrage'and r.thrower==PEER)
assert(count('CUSTOM MP CALL: peer '..PEER..', custom orbital_gas_barrage')==1)
assert(cmp.remote_beacon(world,{entity=7777,type=125},carriers)==nil,'reported once per beacon')
-- A record the game rebuilt (an index first seen holding another type than the token): both types count as native.
W.write(other+R.state+R.entries+0*R.entryStride,W.u32(41))
local rebuilt=cmp.native(world,{},118)
assert(rebuilt.present[loadout.id_of(world,136)]and rebuilt.present[loadout.id_of(world,41)]and#rebuilt.changed==1,
    table.concat(rebuilt.changed,'|'))
W.write(other+R.state+R.entries+0*R.entryStride,W.u32(136))
-- Not a carrier: nothing.
assert(cmp.remote_beacon(world,{entity=7778,type=136},carriers)==nil)
-- The picks line: this machine's own slots and the peer's (reconstructed, or the token).
cmp.picks(world,nil,118,carriers,{[0]='hmg_sentry'})
assert(count('CUSTOM MP PICKS: ')>=2 and count('(you) slot 0 = hmg_sentry')==1
    and count(PEER..' slot 1 = orbital_gas_barrage (reconstructed')==1,table.concat(logged,' | '))
return 'ok'
''')


class LobbyViewTests(unittest.TestCase):
    def test_the_lobby_view_shows_every_players_slots_with_the_token_for_a_custom_pick(self):
        from test_stratagem_selector import SELECT
        self.assertEqual(run(WORLD + SELECT + r'''
local cmp=require('hd2runtime/runtime/custom_multiplayer');cmp.reset_for_tests()
SCREEN=W.loadout_screen({entries={{type=136},{type=118}},players=2})
local world=world_module.open()
-- The other player's record on this machine's loadout screen: the token (their custom pick or a native one) and a
-- native stratagem.
local LO=SEL.loadout
local other=SCREEN.ui+LO.records+1*LO.recordStride
W.write(other+LO.entries+LO.entryType,W.u32(118));W.write(other+LO.entries+LO.entryStride+LO.entryType,W.u32(41))
W.write(other+LO.count,W.u32(2))
local list=assert(selector.lobby_records(world))
assert(#list==2 and list[1]['local']and not list[2]['local'])
assert(list[1].types[2]==118 and list[2].types[1]==118 and list[2].types[2]==41 and list[2].owner=='0000000000007702',
    tostring(list[2].owner))
cmp.lobby(world,118)
assert(count('CUSTOM MP LOBBY (the loadout screen, read-only): player 0 (0000000000007701, you): slot 0 = ')==1,
    table.concat(logged,' | '))
assert(count('player 1 (0000000000007702): slot 0 = ')==1 and count('(the token)')==1)
cmp.lobby(world,118)
assert(count('CUSTOM MP LOBBY')==1,'logged on change only')
return 'ok'
'''), b'ok')


class MissionTests(unittest.TestCase):
    STUB = r'''
local I=custom.internals_for_tests()
local mpm=require('hd2runtime/runtime/multiplayer');mpm.reset_for_tests()
require('hd2runtime/runtime/custom_multiplayer').reset_for_tests()
local selector=require('hd2runtime/runtime/stratagem_selector')
local PRECISION=require('hd2runtime/domains/stratagem_authoring').stratagems['Orbital Precision Strike'].root.id
selector.set_virtual_slots_for_tests({slots={[0]={definition='hmg_sentry',token=PRECISION,type=118},
    [1]={definition='hmg_sentry',token=PRECISION,type=118}},pairs={PRECISION,PRECISION}})
require('hd2runtime/runtime/carrier_allocator').allocate_lobby=function(world,defs,lobby,exclude,opts)
    return {ready=true,refused={eagle_stun_rocket_pods='test: none'},order={'eagle_stun_rocket_pods','hmg_sentry'},
        assignments={hmg_sentry={label='HMG',carrier='A/FLAM-40 Flame Sentry',stable_id=474724029,type=8,
            family='sentry',beam='blue',owned=true}},verdicts={},candidates={},line='CUSTOM CARRIERS: test',
        reservations={[474724029]='hmg_sentry'}}
end
W.players({{peer=0x1111},{peer=0x2222}},0x1111)
'''

    def test_a_client_refuses_its_own_calls_and_observes_the_others(self):
        self.assertEqual(examples_lua(self.STUB + r'''
W.state(4,{host=false})
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(#M.queue==0,'a client queued its own custom stratagem')
assert(count('CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL: 2 players (a mission)')==1,table.concat(logged,' | '))
assert(count('MISSION: custom stratagems REFUSED on this machine: it is a client (2 players)')==1)
assert(count('Your custom slot stays the token Orbital Precision Strike')==1,table.concat(logged,' | '))
assert(M.watch and M.watch.label=='custom stratagems (observing)')
assert(count('CUSTOM MP CARRIERS (mission start')==1 and count('hmg_sentry = A/FLAM-40 Flame Sentry')==1)
assert(count('CUSTOM MP PEERS (mission start): 2 players')==1,table.concat(logged,' | '))
-- Another machine's carrier beacon (no state here): reported, nothing created.
I.beacon_event({kind='created',beacon={entity=7777,type=8,landed=false,timing={}}})
assert(#M.calls==0)
assert(count('CUSTOM MP CALL: peer unknown (no remote record holds the carrier')==1
    and count('custom hmg_sentry (carrier')==1,table.concat(logged,' | '))
-- Announced once only.
I.start_mission(world)
assert(count('CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL')==1)
return 'ok'
'''), b'ok')

    def test_the_host_runs_its_own_calls_each_with_its_own_state_and_scope(self):
        self.assertEqual(examples_lua(self.STUB + r'''
W.state(4,{host=true})
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(#M.queue==1 and M.queue[1].definition.id=='hmg_sentry'and#M.queue[1].slots==2,tostring(#M.queue))
assert(count('REFUSED on this machine')==0 and M.watch and M.watch.label=='custom stratagems')
assert(count('custom stratagem EXPERIMENTAL CUSTOM MP FAIL-CLOSED BUILD r9 (custom-mp/1;')==1,'the build line, once')
assert(count('CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL: 2 players (a mission)')==1)
-- Two calls of one id (its two slots): one shared carrier identity; every call its own id, slot and scope.
local d=custom.get('hmg_sentry')
local a=M.queue[1].assignment
local c1,c2=I.new_call(d,a,0),I.new_call(d,a,1)
assert(c1.carrier.stable_id==c2.carrier.stable_id and c1.call_id~=c2.call_id and c1.slot==0 and c2.slot==1)
assert(mpm.call_allowed(c1)and mpm.call_allowed(c2)and c1.player_peer=='0000000000001111')
-- This machine's own beacon of the carrier (state here): its call, logged for the lobby with the caller.
M.by_type[8]={definition=d,assignment=a}
require('hd2runtime/runtime/beacon_redirect').beacons=function()return {[7005]={type=8,mode=1}}end
I.beacon_event({kind='created',beacon={entity=7005,type=8,landed=true,timing={}}})
local ctx=M.calls_by_beacon[7005]
assert(ctx and ctx.call_id=='hmg_sentry#1'and mpm.call_allowed(ctx))
assert(count('CUSTOM MP CALL: peer 0000000000001111 (you, host), custom hmg_sentry, call hmg_sentry#1')==1,
    table.concat(logged,' | '))
-- Another machine's beacon of the same carrier: reported, never joined to a call of this machine.
local calls=#M.calls
I.beacon_event({kind='created',beacon={entity=7006,type=8,landed=false,timing={}}})
assert(#M.calls==calls and not M.calls_by_beacon[7006])
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
