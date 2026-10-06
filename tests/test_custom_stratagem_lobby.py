"""Custom stratagems in a lobby (development; runtime/carrier_allocator.lua "the lobby"; multiplayer custom stratagems
are NOT supported yet: the mission refuses them):
  * carrier allocation by custom stratagem IDENTITY: every peer allocates every registered custom stratagem by id, so
    every player selecting one id uses one carrier, two ids never share one, natively selected carriers are skipped by
    everybody, and the result never depends on player order, selection order or the account's ownership;
  * the lobby's native selections: every stratagem record the game holds (one per peer), read-only;
  * a shared carrier identity is not shared call state: each call keeps its own call id, beacon, capture, configured
    entity, barrage and association; another machine's beacon of the shared carrier is never this player's call."""
import unittest

from support import run
from test_custom_stratagem_api import ALLOCATION
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_custom_payloads import examples_lua

LOBBY = ALLOCATION + r"""
local HMG={id='hmg_sentry',label='HMG Sentry',token='Orbital Precision Strike',
    policy={beacon='support',prefer_families={'sentry'},allow_families={'sentry'}}}
local REGISTERED={GAS,PELICAN,EAT,HMG}
local EXCLUDE={'Orbital Gas Strike','EAT-17 Expendable Anti-Tank'}
local GATLING,B380,SENTRY=2084654169,3108516875,222
local function lobby(selections,present,players,definitions)
    return A.allocate_lobby(nil,definitions or REGISTERED,{present=present or{},players=players or#selections,
        selections=selections},EXCLUDE)
end
-- {player = {id = carrier}} of a mapping.
local function carriers(a)
    local out={}
    for _,row in ipairs(a.mapping)do
        local m={}
        for _,s in ipairs(row.slots)do m[s.id]=s.carrier or('REFUSED '..tostring(s.refused))end
        out[row.player]=m
    end
    return out
end
local function key(a)
    local parts={}
    for _,id in ipairs({'eat17_gas','hmg_sentry','orbital_gas_barrage','pelican_close_air_support'})do
        local x=a.assignments[id]
        parts[#parts+1]=id..'='..tostring(x and x.carrier)
    end
    return table.concat(parts,'; ')
end
"""


class LobbyAllocationTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(LOBBY + body), b'ok')

    def test_one_custom_stratagem_shares_one_carrier_across_players(self):
        self.lua(r'''
CANDIDATES=full()
local a=lobby({{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'orbital_gas_barrage'}}})
local c=carriers(a)
assert(c.P1.orbital_gas_barrage=='Orbital Gatling Barrage'and c.P2.orbital_gas_barrage=='Orbital Gatling Barrage')
-- One reservation, reused by the second player.
assert(a.mapping[1].slots[1].reused==false and a.mapping[2].slots[1].reused==true)
assert(a.reservations[GATLING]=='orbital_gas_barrage')
-- Three players: still the one carrier.
local b=lobby({{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'orbital_gas_barrage'}},
    {player='P3',ids={'orbital_gas_barrage'}}})
local cb=carriers(b)
assert(cb.P1.orbital_gas_barrage==cb.P2.orbital_gas_barrage and cb.P2.orbital_gas_barrage==cb.P3.orbital_gas_barrage
    and cb.P3.orbital_gas_barrage=='Orbital Gatling Barrage')
return 'ok'
''')

    def test_different_custom_stratagems_never_share_and_a_reserved_carrier_is_skipped(self):
        self.lua(r'''
CANDIDATES=full()
local a=lobby({{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'pelican_close_air_support'}}})
local c=carriers(a)
assert(c.P1.orbital_gas_barrage=='Orbital Gatling Barrage'and c.P2.pelican_close_air_support=='Orbital 380mm HE Barrage')
-- The Pelican skipped the carrier another custom stratagem reserved.
assert(a.verdicts.pelican_close_air_support[GATLING]=='taken by Gas Barrage (never shared)')
-- Two players' Gas Barrage and a third player's HMG Sentry: one shared Gas carrier, one HMG carrier.
local b=lobby({{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'orbital_gas_barrage'}},
    {player='P3',ids={'hmg_sentry'}}})
local cb=carriers(b)
assert(cb.P1.orbital_gas_barrage=='Orbital Gatling Barrage'and cb.P2.orbital_gas_barrage=='Orbital Gatling Barrage')
assert(cb.P3.hmg_sentry=='A/MG-43 Machine Gun Sentry')
local n=0;for _ in pairs(b.reservations)do n=n+1 end
assert(n==4 and b.distinct,'every registered custom stratagem holds one distinct carrier')
return 'ok'
''')

    def test_a_carrier_natively_selected_by_any_player_is_skipped_identically_by_every_peer(self):
        self.lua(r'''
CANDIDATES=full()
-- P2 brings the Orbital Gatling Barrage natively: in the lobby's native set, every peer skips it.
local present={[GATLING]=true}
local selections={{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={}},
    {player='P3',ids={'orbital_gas_barrage','pelican_close_air_support'}}}
local p1=lobby(selections,present,3)
assert(carriers(p1).P1.orbital_gas_barrage=='Orbital 380mm HE Barrage')
assert(p1.verdicts.orbital_gas_barrage[GATLING]:find('in the loadout',1,true))
-- The Pelican: no red carrier left (the Gatling natively selected, the 380mm the Gas Barrage's): refused, everywhere.
assert(carriers(p1).P3.pelican_close_air_support:find('^REFUSED'))
-- Every peer evaluates the same lobby (its own selections listed first, the definitions in another order): identical.
local p2=lobby({selections[2],selections[3],selections[1]},present,3,{HMG,EAT,PELICAN,GAS})
local p3=lobby({selections[3],selections[1],selections[2]},present,3,{PELICAN,HMG,GAS,EAT})
assert(key(p1)==key(p2)and key(p2)==key(p3),key(p1)..' / '..key(p2)..' / '..key(p3))
assert(carriers(p2).P1.orbital_gas_barrage=='Orbital 380mm HE Barrage'and carriers(p3).P1.orbital_gas_barrage
    =='Orbital 380mm HE Barrage')
return 'ok'
''')

    def test_the_allocation_never_depends_on_player_or_selection_order(self):
        self.lua(r'''
CANDIDATES=full()
local s1={{player='P1',ids={'orbital_gas_barrage','eat17_gas'}},{player='P2',ids={'pelican_close_air_support'}},
    {player='P3',ids={'hmg_sentry','orbital_gas_barrage'}}}
local s2={s1[3],s1[1],s1[2]}
local a=lobby(s1,{},3,{GAS,PELICAN,EAT,HMG})
local b=lobby(s2,{},3,{HMG,EAT,PELICAN,GAS})
assert(key(a)==key(b),key(a)..' / '..key(b))
local ca,cb=carriers(a),carriers(b)
for _,player in ipairs({'P1','P2','P3'})do
    for id,carrier in pairs(ca[player])do assert(cb[player][id]==carrier,player..' '..id)end
end
-- Nor on what is selected: the carrier of an id is the same whoever selects what.
local c=lobby({{player='P1',ids={'pelican_close_air_support'}}},{},1)
assert(c.assignments.pelican_close_air_support.carrier==a.assignments.pelican_close_air_support.carrier)
return 'ok'
''')

    def test_four_players_selecting_one_custom_stratagem_use_its_one_carrier(self):
        self.lua(r'''
CANDIDATES=full()
local sel={}
for k=1,4 do sel[k]={player='P'..k,ids={'hmg_sentry'}}end
local a=lobby(sel,{},4)
local c=carriers(a)
for k=1,4 do assert(c['P'..k].hmg_sentry=='A/MG-43 Machine Gun Sentry','P'..k)end
-- One reservation: made for the first row, reused by the three others.
local reused=0
for k=1,4 do if a.mapping[k].slots[1].reused then reused=reused+1 end end
assert(reused==3 and a.reservations[SENTRY]=='hmg_sentry')
-- The other registered ids keep their own carriers (allocated whether or not anyone selects them).
assert(a.assignments.orbital_gas_barrage.carrier=='Orbital Gatling Barrage'
    and a.assignments.pelican_close_air_support.carrier=='Orbital 380mm HE Barrage'
    and a.assignments.eat17_gas.carrier=='MG-43 Machine Gun')
return 'ok'
''')

    def test_the_same_id_reuses_its_reservation_and_another_id_finds_it_unavailable(self):
        self.lua(r'''
CANDIDATES=full()
local a=lobby({{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'orbital_gas_barrage'}},
    {player='P3',ids={'pelican_close_air_support'}},{player='P4',ids={'pelican_close_air_support','eat17_gas'}}},{},4)
local c=carriers(a)
assert(c.P1.orbital_gas_barrage=='Orbital Gatling Barrage'and c.P2.orbital_gas_barrage=='Orbital Gatling Barrage')
assert(c.P3.pelican_close_air_support=='Orbital 380mm HE Barrage'and c.P4.pelican_close_air_support
    =='Orbital 380mm HE Barrage'and c.P4.eat17_gas=='MG-43 Machine Gun')
-- The Gas Barrage's carrier is unavailable to the Pelican (never shared), whoever selects which.
assert(a.verdicts.pelican_close_air_support[GATLING]=='taken by Gas Barrage (never shared)')
assert(a.reservations[GATLING]=='orbital_gas_barrage'and a.reservations[B380]=='pelican_close_air_support')
for _,row in ipairs(a.mapping)do
    for _,s in ipairs(row.slots)do
        assert(s.stable_id and a.reservations[s.stable_id]==s.id,
            row.player..' '..s.id..' uses another id\'s carrier')
    end
end
return 'ok'
''')

    def test_every_shuffled_player_and_definition_order_gives_one_mapping(self):
        self.lua(r'''
CANDIDATES=full()
local rows={{player='P1',ids={'orbital_gas_barrage','eat17_gas'}},{player='P2',ids={'pelican_close_air_support'}},
    {player='P3',ids={'hmg_sentry','orbital_gas_barrage'}},{player='P4',ids={'eat17_gas','pelican_close_air_support'}}}
local function permutations(list)
    local out={}
    local function go(prefix,rest)
        if#rest==0 then out[#out+1]=prefix;return end
        for k=1,#rest do
            local p,r={},{}
            for _,v in ipairs(prefix)do p[#p+1]=v end
            p[#p+1]=rest[k]
            for j,v in ipairs(rest)do if j~=k then r[#r+1]=v end end
            go(p,r)
        end
    end
    go({},list)
    return out
end
local function flat(a)
    local c,parts=carriers(a),{}
    for k=1,4 do
        local m,ids=c['P'..k],{}
        for id in pairs(m)do ids[#ids+1]=id end
        table.sort(ids)
        for _,id in ipairs(ids)do parts[#parts+1]='P'..k..':'..id..'='..m[id]end
    end
    return key(a)..' | '..table.concat(parts,',')
end
local first
local defs={{GAS,PELICAN,EAT,HMG},{HMG,EAT,PELICAN,GAS},{PELICAN,GAS,HMG,EAT}}
local n=0
for _,order in ipairs(permutations(rows))do
    -- Each row's own ids shuffled too (reversed every other time).
    local shuffled={}
    for k,row in ipairs(order)do
        local ids={}
        for j=#row.ids,1,-1 do ids[#ids+1]=row.ids[j]end
        shuffled[k]=n%2==0 and row or{player=row.player,ids=ids}
    end
    for _,d in ipairs(defs)do
        local f=flat(lobby(shuffled,{},4,d))
        first=first or f
        assert(f==first,f..'\n'..first)
        n=n+1
    end
end
assert(n==72)
return 'ok'
''')

    def test_ownership_never_changes_the_lobby_mapping_and_refuses_locally(self):
        self.lua(r'''
-- This account does not own the Orbital Gatling Barrage (only its ownership stands in the way).
CANDIDATES=full()
CANDIDATES[1].eligible=false;CANDIDATES[1].reasons={'not owned'};CANDIDATES[1].codes={'not_owned'}
local sel={{player='P1',ids={'orbital_gas_barrage'}},{player='P2',ids={'orbital_gas_barrage'}}}
local mine=lobby(sel,{},2)
-- The lobby's carrier stays the Gatling (every peer agrees); here it is refused, never replaced.
assert(mine.assignments.orbital_gas_barrage.carrier=='Orbital Gatling Barrage')
assert(mine.assignments.orbital_gas_barrage.owned==false and mine.assignments.orbital_gas_barrage.local_refused
    :find('this account does not own',1,true))
assert(mine.assignments.pelican_close_air_support.carrier=='Orbital 380mm HE Barrage')
-- A peer that owns it: the same mapping.
CANDIDATES=full()
local theirs=lobby(sel,{},2)
assert(key(theirs)==key(mine),key(theirs)..' / '..key(mine))
assert(theirs.assignments.orbital_gas_barrage.owned==true and not theirs.assignments.orbital_gas_barrage.local_refused)
-- Alone (one account), ownership filters as it always did.
CANDIDATES=full()
CANDIDATES[1].eligible=false;CANDIDATES[1].reasons={'not owned'};CANDIDATES[1].codes={'not_owned'}
local solo=lobby({{player='P1',ids={'orbital_gas_barrage'}}},{},1)
assert(solo.assignments.orbital_gas_barrage.carrier=='Orbital 380mm HE Barrage')
return 'ok'
''')


RECORDS = r"""
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local A=require('hd2runtime/runtime/carrier_allocator')
local R=require('hd2runtime/domains/stratagem_slots').record
-- Two players' records in the game's per-peer array: the local player's (the fixture's) and a peer's.
local function two_records(h,peer_types)
    local base=b.pointer(W.read(W.GAME+R.global,8),0)
    local records=W.alloc(R.count+8)
    W.write(records,W.read(base,R.stride))
    local other=records+R.stride
    W.write(other,W.u32(0x99990000)..W.u32(0x00000002))
    for k,kind in ipairs(peer_types)do W.write(other+R.state+R.entries+(k-1)*R.entryStride,W.u32(kind))end
    W.write(other+R.state+R.entryCount,W.u32(#peer_types))
    W.write(records+R.count,W.u32(2))
    W.write(W.GAME+R.global,W.u64(records))
    return records
end
"""


class LobbyRecordsTests(unittest.TestCase):
    def test_every_peers_record_is_read_and_unioned_into_the_native_set(self):
        self.assertEqual(run(WORLD + SLOT + RECORDS + r'''
local h=world_with()
local world=world_module.open()
local one=assert(slots.records(world))
assert(#one==1 and one[1]['local'],'one: '..#one..' '..tostring(one[1]and one[1].peer))
local records=two_records(h,{106,136})
local list=assert(slots.records(world))
assert(#list==2,'records '..#list)
-- Sorted by peer id, the local one marked; each with its own entries.
assert(list[1].peer<list[2].peer,list[1].peer..' '..list[2].peer)
local mine,other
for _,r in ipairs(list)do if r['local']then mine=r else other=r end end
assert(mine and other and other.peer=='0000000299990000'and #other.entries==2 and other.entries[1].type==106,
    tostring(other and other.peer)..' '..tostring(other and #other.entries))
-- The lobby's native set: the saved loadout and every record's entries.
local lobby=A.lobby_native(world,{[12345]=true})
assert(lobby.records==2 and lobby.present[12345],'lobby '..lobby.records)
local loadout=require('hd2runtime/runtime/stratagem_loadout')
-- The peer's 120mm (type 136) is in it; a type with no row here (106) is skipped.
assert(loadout.id_of(world,106)==nil and lobby.present[loadout.id_of(world,136)])
-- Another player's record present: a write path that is not a custom stratagem call's keeps the solo guard (here the
-- duplicate-token conversion); neither record changes. Only a custom stratagem call accepts the experimental scope.
W.guarded_runtime()
local mine_before=W.read(records,R.stride)
local other_before=W.read(records+R.stride,R.stride)
local writes=#(W.runtime.writes or{})
local job=settle_job(slots.convert({token='Orbital Precision Strike',carrier='Orbital 120mm HE Barrage'}))
assert(job.status~='converted'and job.code=='NOT_SOLO',tostring(job.status)..' '..tostring(job.code))
assert(#(W.runtime.writes or{})==writes and W.read(records,R.stride)==mine_before
    and W.read(records+R.stride,R.stride)==other_before)
return 'ok'
'''), b'ok')


class CallStateTests(unittest.TestCase):
    def test_a_shared_carrier_identity_is_never_shared_call_state(self):
        # Two calls of one custom stratagem (as two players' calls of one shared carrier would be): each its own call
        # id, beacon, capture, configured sentry and association; the carrier assignment is the one shared identity.
        self.assertEqual(examples_lua(r'''
local I=custom.internals_for_tests()
local pods=require('hd2runtime/runtime/support_pods')
local weapons=require('hd2runtime/runtime/custom_weapons')
local s=custom.get('hmg_sentry')
local G=require('hd2runtime/domains/stratagem_authoring').stratagems['A/MG-43 Machine Gun Sentry'].root
settings=W.stratagem_settings({{type=60,id=G.id,package=G.package,payloads=G.payloads,sequence={3,1,2,4},
    group=G.group,row=G.row,cooldown=150}})
local specs,configured={},{}
pods.capture=function(spec,cb)
    specs[#specs+1]=spec
    local sentry=spec.beacon_network==801 and 9801 or 9802
    cb({kind='pod',pod=sentry-1000})
    cb({kind='captured',pod=sentry-1000,rack=sentry,content=sentry,items={sentry},types={'37CDE43876BA26BB'}})
    return {status='complete'}
end
weapons.configure=function(world,entity,spec,label)
    configured[#configured+1]={entity=entity,label=label}
    return {writes=12,verified=true,verify={}}
end
local carrier={carrier='A/FLAM-40 Flame Sentry',stable_id=474724029,type=8}
local c1=I.new_call(s,carrier,1)
local c2=I.new_call(s,carrier,2)
c1.beacon={entity=7005,network=801}
c2.beacon={entity=7006,network=802}
I.start_capture(c1,s)
I.start_capture(c2,s)
-- Shared: the carrier identity. Independent: everything of each call.
assert(c1.carrier.stable_id==c2.carrier.stable_id and c1.carrier.name==c2.carrier.name)
assert(c1.call_id=='hmg_sentry#1'and c2.call_id=='hmg_sentry#2'and c1~=c2)
assert(specs[1].beacon_network==801 and specs[2].beacon_network==802)
assert(c1.sentry.entity==9801 and c2.sentry.entity==9802)
assert(configured[1].entity==9801 and configured[1].label:find('hmg_sentry#1',1,true)
    and configured[2].entity==9802 and configured[2].label:find('hmg_sentry#2',1,true))
assert(custom.instance_of(9801).call_id=='hmg_sentry#1'and custom.instance_of(9802).call_id=='hmg_sentry#2')
assert(c1.slot==1 and c2.slot==2)
return 'ok'
'''), b'ok')

    def test_two_barrage_calls_run_their_own_barrages_and_another_machines_beacon_is_ignored(self):
        self.assertEqual(examples_lua(r'''
local I=custom.internals_for_tests()
local executor=require('hd2runtime/runtime/bombardment_executor')
-- An orbital definition (registered here as data).
local hd2=require('hd2runtime/api/hd2')
local events=require('hd2runtime/runtime/events')
events.run_as('mods/test/orbital',hd2.custom_stratagem.register,{id='ems_rain',name='EMS RAIN',name_cased='EMS Rain',
    description='A test barrage.',icon='hmg_sentry',code={'up','up','up','down','down','down'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    orbital={shell='Orbital EMS Strike',pattern='Orbital 120mm HE Barrage',salvos=2,shells_per_salvo=2}})
local d=custom.get('ems_rain')
local started={}
executor.start=function(spec,cb)started[#started+1]=spec;return {status='active'}end
local carrier={carrier='Orbital 380mm HE Barrage',stable_id=3108516875,type=125}
local c1=I.new_call(d,carrier,0)
local c2=I.new_call(d,carrier,1)
c1.position={x=1,y=2,z=3};c2.position={x=40,y=50,z=6}
assert(c1:barrage({shell='Orbital EMS Strike',pattern='Orbital 120mm HE Barrage'}))
assert(c2:barrage({shell='Orbital EMS Strike',pattern='Orbital 120mm HE Barrage'}))
assert(#started==2 and started[1].label=='ems_rain#1'and started[2].label=='ems_rain#2')
assert(started[1].target.x==1 and started[2].target.x==40,'a barrage took another call\'s position')
-- Another machine's beacon of the shared carrier (no state here): not this player's call; no context, no callback.
local M=I.mission()
M.by_type[125]={definition=d,assignment=carrier}
local redirect=require('hd2runtime/runtime/beacon_redirect')
redirect.beacons=function()return {[7777]={type=125,mode=nil}}end
local calls=#M.calls
I.beacon_event({kind='created',beacon={entity=7777,type=125,timing={}}})
assert(#M.calls==calls and not M.calls_by_beacon[7777])
assert(count('BEACON 7777 of the carrier Orbital 380mm HE Barrage is another machine\'s (no state here): another '
    ..'player\'s call, not this player\'s; ignored')==1,table.concat(logged,' | '))
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
