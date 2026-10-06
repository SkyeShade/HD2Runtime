"""Custom multiplayer at mission start (runtime/custom_stratagems.lua mp_step; runtime/custom_mp_sync.lua;
docs/research/runtime-peer-messaging-F5FEE03DCFDB.md section 10), with the synced view and the records stubbed:
  * the carriers come from the synced table only (the ids the lobby selects), with every custom slot's entry excluded
    from the native picks; the host publishes the table and carrier hashes and runs its own calls of every family;
  * a client waits for the host's hashes: equal, it runs its own calls of the client families (the Gas EAT and the HMG
    Sentry here, every write marked for the client-write proof); different or never published: nothing runs;
  * a custom slot whose record entry holds neither the token nor its id's carrier is a CUSTOM MP DESYNC: this machine's
    own such id does not run;
  * the synced allocation itself: one carrier per id however many players and slots select it, distinct ids distinct
    carriers, a native pick anywhere never a carrier, and the same map and hash whatever the order;
  * hd2.ownership.credit_to_player identifies the call's player by its peer id (it always refused before)."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_custom_stratagem_lobby import LOBBY


def example_addon(name):
    from test_event_scripting import SDK
    folder = ROOT / 'proof' / name
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


def mission_lua(body):
    from support import lua as lua_literal
    (eat, eat_addon), (sentry, sentry_addon) = example_addon('GasEatExample'), example_addon('HmgSentryExample')
    return run(WORLD + 'local EAT_ADDON=' + lua_literal(eat_addon) + '\nlocal EAT_RESOURCE=' + lua_literal(eat)
        + '\nlocal SENTRY_ADDON=' + lua_literal(sentry_addon) + '\nlocal SENTRY_RESOURCE=' + lua_literal(sentry) + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
require('hd2runtime/runtime/spawned_instances').reset_for_tests()
assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()
assert(loadstring(SENTRY_ADDON,'@'..SENTRY_RESOURCE))()
local I=custom.internals_for_tests()
local mpm=require('hd2runtime/runtime/multiplayer');mpm.reset_for_tests()
local cmp=require('hd2runtime/runtime/custom_multiplayer');cmp.reset_for_tests()
local sync=require('hd2runtime/runtime/custom_mp_sync')
local P=require('hd2runtime/runtime/peer_protocol')
local selector=require('hd2runtime/runtime/stratagem_selector')
local PRECISION=require('hd2runtime/domains/stratagem_authoring').stratagems['Orbital Precision Strike'].root.id
local ME,THEM='0000000000001111','0000000000002222'
-- This player: Gas EAT twice (slots 0 and 2) and the HMG Sentry (slot 1); slot 3 native.
selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17_gas',token=PRECISION,type=118},
    [1]={definition='hmg_sentry',token=PRECISION,type=118},[2]={definition='eat17_gas',token=PRECISION,type=118}},
    pairs={PRECISION,PRECISION,PRECISION,1}})
-- The allocator: an EAT-17-free support carrier for the Gas EAT, a sentry carrier for the HMG; what it was given.
local GIVEN
require('hd2runtime/runtime/carrier_allocator').allocate_lobby=function(world,defs,lobby,exclude,opts)
    GIVEN={defs=defs,present=lobby.present}
    local a={ready=true,refused={},order={},assignments={},verdicts={},candidates={},line='CUSTOM CARRIERS: test',
        reservations={}}
    for _,d in ipairs(defs)do
        a.order[#a.order+1]=d.id
        if d.id=='eat17_gas'then
            a.assignments[d.id]={label='Gas EAT',carrier='M-105 Stalwart',stable_id=902,type=9,family='support',owned=true}
        elseif d.id=='hmg_sentry'then
            a.assignments[d.id]={label='HMG',carrier='A/FLAM-40 Flame Sentry',stable_id=474724029,type=8,family='sentry',
                owned=true}
        end
    end
    return a
end
W.players({{peer=0x1111},{peer=0x2222}},0x1111)
-- The synced view: both players' picks (the other player: one Gas EAT in slot 0).
local V={status='enabled',members={ME,THEM},local_peer=ME,host_peer=THEM,is_host=false,lobby='cv2:test',
    table={[ME]={[0]='eat17_gas',[1]='hmg_sentry',[2]='eat17_gas',[3]=false},[THEM]={[0]='eat17_gas',[1]=false,
    [2]=false,[3]=false}}}
V.table_hash=P.table_hash(V.table)
V.local_seq,V.local_posted,V.peers=3,true,{[THEM]={state='compatible',seq=7}}
sync.view=function()return V end
-- Every player's record as first seen: a granted default (124), then the loadout (118: the token).
local function rec(peer,types)
    local e={{index=0,type=124,granted=1}}
    for k,t in ipairs(types)do e[#e+1]={index=k,type=t,granted=0}end
    return {peer=peer,entries=e}
end
local RECORDS={rec(ME,{118,118,118,22}),rec(THEM,{118,41,130})}
cmp.first_records=function()return RECORDS end
local function ids(defs)local out={};for k,d in ipairs(defs)do out[k]=d.id end;table.sort(out);return table.concat(out,',')end
''' + body)


class MissionStartTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(mission_lua(body + "\nreturn 'ok'"), b'ok')

    def test_a_client_runs_its_gas_eat_and_its_sentry_once_it_agrees_with_the_host(self):
        self.lua(r"""
W.state(4,{host=false})
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(M.mp and M.mp.state=='agreement',tostring(M.mp and M.mp.state))
-- The carriers from the synced table only; the custom slots are not native picks, every other entry is.
assert(ids(GIVEN.defs)=='eat17_gas,hmg_sentry',ids(GIVEN.defs))
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local function native(t)local id=loadout.id_of(world,t);return id and GIVEN.present[id]end
assert(native(22)and native(41)and native(130)and not native(118),'the native picks')
assert(count('CUSTOM MP CARRIERS (mission start; table hash '..V.table_hash..'): eat17_gas = M-105 Stalwart (stable id '
    ..'902), hmg_sentry = A/FLAM-40 Flame Sentry (stable id 474724029)')==1,table.concat(logged,' | '))
assert(#M.queue==0 and not mpm.client_proof(),'nothing runs before the agreement')
-- The host has not published: waiting.
I.mp_step(world)
assert(M.mp.state=='agreement')
-- The host's hashes, equal: the client-write proof runs the Gas EAT and the HMG Sentry (both client families).
V.host_hashes={table=V.table_hash,carrier=M.mp.carrier_hash}
I.mp_step(world)
assert(M.mp.state=='running'and mpm.client_proof()and M.client==true)
local queued={}
for _,item in ipairs(M.queue)do queued[item.definition.id]=item end
assert(#M.queue==2 and queued.eat17_gas and queued.hmg_sentry,tostring(#M.queue))
assert(queued.eat17_gas.client==true and#queued.eat17_gas.slots==2 and queued.hmg_sentry.client==true)
assert(count('CUSTOM MP AGREEMENT (mission start): table hash '..V.table_hash..', carrier hash '..M.mp.carrier_hash
    ..': this client agrees with the session host '..THEM)==1)
assert(count('MISSION (hmg_sentry): REFUSED on this client')==0)
-- Its calls carry the client mark into every write: the beacon's decision, the call context.
M.by_type[9]=queued.eat17_gas
local change=I.decide({type=9})
assert(change.delivery=='EAT-17 Expendable Anti-Tank'and change.client==true)
local d=custom.get('eat17_gas')
local ctx=I.new_call(d,queued.eat17_gas.assignment,0)
assert(ctx.client==true and mpm.call_allowed(ctx))
""")

    def test_a_client_runs_nothing_when_the_host_differs_or_never_publishes(self):
        self.lua(r"""
W.state(4,{host=false})
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
V.host_hashes={table=V.table_hash,carrier='00000000'}
I.mp_step(world)
assert(M.mp.state=='refused'and#M.queue==0 and not mpm.client_proof())
assert(count('custom multiplayer REFUSED on this machine: the carrier hash differs from the session host\'s (mine '
    ..M.mp.carrier_hash..', the host\'s 00000000)')==1,table.concat(logged,' | '))
-- Never published within the timeout.
custom.reset_for_tests()
I=custom.internals_for_tests()
V.host_hashes=nil
I.start_mission(world)
M=I.mission()
M.clock=M.clock+custom.AGREEMENT_TIMEOUT+1
I.mp_step(world)
assert(M.mp.state=='refused'and count('published no matching hashes within 60 s')==1)
""")

    def test_the_teammate_hud_overlay_reads_the_frozen_table_only_while_running(self):
        # runtime/stratagem_slot_overlay.lua mission_remote_slots (tests/test_teammate_hud_overlay.py): its source is
        # every OTHER player's slots of the mission's frozen table and the frozen carrier map, nothing otherwise.
        self.lua(r"""
local T=assert(I.teammates(),'the teammate HUD follower is started with the loop')
assert(T.source()==nil,'aboard the ship: nothing')
W.state(4,{host=false})
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(M.mp.state=='agreement'and T.source()==nil,'not running yet: nothing')
V.host_hashes={table=V.table_hash,carrier=M.mp.carrier_hash}
I.mp_step(world)
assert(M.mp.state=='running','running: '..tostring(M.mp.state))
local synced,carriers=T.source()
assert(synced and synced[ME]==nil and synced[THEM][0]=='eat17_gas'and synced[THEM][1]==false,'the other player only')
assert(carriers==M.carrier_types and carriers[9]=='eat17_gas','the frozen carrier map')
-- A later lobby view (a new view object) does not change the mission's table.
sync.view=function()return {table={[THEM]={[0]='hmg_sentry'}},peers={},local_peer=ME}end
assert(T.source()[THEM][0]=='eat17_gas','the frozen table')
-- That player rejoins with an incompatible Runtime: left out (no view, or a missing state, keeps the frozen table).
sync.view=function()return {peers={[THEM]={state='incompatible'}},local_peer=ME}end
assert(T.source()==nil,'an incompatible player is left out')
sync.view=function()return nil end
assert(T.source()[THEM][0]=='eat17_gas','no live view: the frozen table')
M.mp.state='refused'
assert(T.source()==nil,'refused: nothing')
""")

    def test_the_host_publishes_the_hashes_and_runs_every_family_of_its_own(self):
        self.lua(r"""
W.state(4,{host=true})
V.is_host,V.host_peer=true,ME
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(M.mp.state=='running'and not mpm.client_proof()and M.client==false)
assert(#M.queue==2 and M.queue[1].client==false and M.queue[2].client==false)
local host=I.mpstate().host
assert(host.table==V.table_hash and host.carrier==M.mp.carrier_hash)
assert(count('this machine is the session host: it publishes table hash '..V.table_hash)==1)
""")

    def test_a_desynced_custom_slot_is_reported_and_its_own_id_does_not_run(self):
        self.lua(r"""
W.state(4,{host=true})
V.is_host,V.host_peer=true,ME
-- The other player's custom slot 0 holds a native stratagem; this player's slot 1 (the HMG) another type.
RECORDS={rec(ME,{118,41,118,22}),rec(THEM,{136,41,130})}
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(count('CUSTOM MP DESYNC: '..THEM..' loadout slot 0: the synced picks say eat17_gas')==1,table.concat(logged,' | '))
assert(count('CUSTOM MP DESYNC: '..ME..' (you) loadout slot 1: the synced picks say hmg_sentry')==1)
assert(#M.queue==1 and M.queue[1].definition.id=='eat17_gas')
assert(count('MISSION (hmg_sentry): REFUSED: loadout slot 1 is DESYNCED')==1)
""")

    def test_a_missing_record_waits_then_refuses(self):
        self.lua(r"""
W.state(4,{host=true})
V.is_host,V.host_peer=true,ME
RECORDS={rec(ME,{118,118,118,22})}
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(M.mp.state=='records')
M.clock=M.clock+custom.RECORDS_TIMEOUT+1
I.mp_step(world)
assert(M.mp.state=='refused'and count('custom multiplayer REFUSED on this machine: no stratagem record of '..THEM
    ..' after 30 s')==1,table.concat(logged,' | '))
-- Every custom slot of this machine named, loudly: not converted, its token locked (0.30 fail closed).
assert(count('CUSTOM MP SETUP REFUSED: loadout slot 0 (eat17_gas) is UNAVAILABLE in this mission')==1
    and count('CUSTOM MP SETUP REFUSED: loadout slot 1 (hmg_sentry)')==1
    and count('CUSTOM MP SETUP REFUSED: loadout slot 2 (eat17_gas)')==1 and count('its token Orbital Precision Strike '
    ..'is LOCKED for this mission (never called)')==3,table.concat(logged,' | '))
-- 0.30 fail closed: no record to lock here (this harness has none): refused loudly, never silently callable.
assert(count('CUSTOM STRATAGEM LOCK FAILED: the stratagem record is unreadable: DO NOT CALL')==1)
""")


class RemoteCallTests(unittest.TestCase):
    def test_another_machines_call_names_its_thrower_from_the_ball_never_a_guess(self):
        self.assertEqual(mission_lua(r"""
W.state(4,{host=true})
V.is_host,V.host_peer=true,ME
local world=world_module.open()
I.start_mission(world)
local M=I.mission()
assert(M.mp.state=='running')
require('hd2runtime/runtime/beacon_redirect').beacons=function()return {[7101]={type=9},[7102]={type=9}}end
local pods=require('hd2runtime/runtime/support_pods')
pods.beacon_network=function(world,it)return it.type==9 and 0x300 or nil end
local observed={}
require('hd2runtime/runtime/custom_mp_observer').remote_support=function(spec)observed[#observed+1]=spec end
local call_ins=require('hd2runtime/runtime/call_ins')
local BALL
call_ins.thrower=function(world,network,records,accept)
    if not BALL then return nil,'no thrown ball names that beacon (yet)'end
    -- The other player's converted slot threw the carrier; its record here still holds the token.
    assert(accept(THEM,0,M.token_type,9)==true and accept(THEM,1,M.token_type,9)==false,'accept')
    return BALL
end
-- The ball is there: its owner is the thrower.
BALL={peer=THEM,entry=1,slot=0,type=9}
I.beacon_event({kind='created',beacon={entity=7101,type=9,landed=false,timing={}}})
assert(count('CUSTOM MP CALL: peer '..THEM..' (the thrown ball\'s owner), custom eat17_gas, slot 0 (its record entry 1), '
    ..'beacon 7101 (network id 768)')==1,table.concat(logged,' | '))
assert(#observed==1 and observed[1].network==0x300 and#M.calls==0,'observed only, nothing of it runs here')
-- No ball yet: retried for 5 s, then the synced table's only other Gas EAT player, labelled as NOT from the ball.
BALL=nil
I.beacon_event({kind='created',beacon={entity=7102,type=9,landed=false,timing={}}})
assert(count('CUSTOM MP CALL: peer')==1 and#M.pending==1)
for _=1,4 do M.clock=M.clock+1;I.pending_step(world)end
assert(count('CUSTOM MP CALL: peer')==1,'no line before the wait ends')
M.clock=M.clock+2;I.pending_step(world)
assert(count('CUSTOM MP CALL: peer '..THEM..' (NOT from the ball: no thrown ball names that beacon (yet); derived from '
    ..'the frozen carrier map: the only other player selecting it), slot 0, custom eat17_gas, beacon 7102')==1,
    table.concat(logged,' | '))
assert(#M.pending==0)
return 'ok'
"""), b'ok')


class SyncedAllocationTests(unittest.TestCase):
    def test_one_carrier_per_selected_id_whatever_the_order(self):
        self.assertEqual(run(LOBBY + r"""
local P=require('hd2runtime/runtime/peer_protocol')
local sync=require('hd2runtime/runtime/custom_mp_sync')
CANDIDATES=full()
-- Three players: Gas EAT on all three (and twice on one), the Gas Barrage on one; the Pelican is registered, not picked.
local t={P1={[0]='eat17_gas',[1]='eat17_gas',[2]='orbital_gas_barrage'},P2={[3]='eat17_gas'},P3={[0]='eat17_gas'}}
local ids=sync.table_ids(t)
assert(table.concat(ids,',')=='eat17_gas,orbital_gas_barrage')
local only={}
for _,d in ipairs(REGISTERED)do for _,id in ipairs(ids)do if d.id==id then only[#only+1]=d end end end
local a=lobby({},{},3,only)
assert(a.assignments.eat17_gas and a.assignments.orbital_gas_barrage and not a.assignments.pelican_close_air_support,
    'only the selected ids get carriers')
assert(a.assignments.eat17_gas.stable_id~=a.assignments.orbital_gas_barrage.stable_id,'distinct ids, distinct carriers')
-- The same definitions in another order: the same map and hash.
local reversed={only[2],only[1]}
local b=lobby({},{},3,reversed)
local function map(x)local m={};for id,y in pairs(x.assignments)do m[id]=y.stable_id end;return m end
assert(P.carrier_hash(map(a))==P.carrier_hash(map(b))and key(a)==key(b))
-- A native pick anywhere in the lobby is never a carrier: the Gas Barrage's carrier, natively selected, is skipped.
local taken=a.assignments.orbital_gas_barrage.stable_id
local c=lobby({},{[taken]=true},3,only)
assert(c.assignments.orbital_gas_barrage.stable_id~=taken,'a native pick became a carrier')
return 'ok'
"""), b'ok')


class OwnershipApiTests(unittest.TestCase):
    def test_credit_to_player_identifies_the_calls_player_by_peer(self):
        self.assertEqual(mission_lua(r"""
local own=require('hd2runtime/api/ownership')
local instances=require('hd2runtime/runtime/spawned_instances')
local ownership=require('hd2runtime/runtime/ownership')
local credited
ownership.credit_to_host=function(world,entity,call_id)credited={entity=entity,call_id=call_id};return {applied=true}end
local scheduler=require('hd2runtime/runtime/scheduler')
local function in_update(fn)
    local out
    local w={status='active'};function w.cancel()w.status='cancelled'end
    function w.tick()out={fn()};w.status='complete'end
    scheduler.attach(w);tick()
    return unpack(out)
end
W.players({{peer=0x1111,avatar=100}},0x1111)
W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true}
W.state(4,{host=true})
local handles=require('hd2runtime/runtime/handles')
local me=handles.local_player()
assert(me and me.peer==ME)
-- An entity associated with this player's call (ctx.player is the Player handle).
W.add{entity=6001,type=W.AVATAR,unit=7101,health=10}
local call={call_id='pelican_close_air_support#1',definition='pelican_close_air_support',n=1,player=me}
mpm.mark_call(call)
assert(instances.associate(6001,call,'pelican'))
local r=in_update(function()return own.credit_to_player(6001,me)end)
assert(r.applied==true and credited and credited.entity==6001 and credited.call_id=='pelican_close_air_support#1',
    tostring(r.reason))
-- Another player's call: still OTHER_PLAYER (the rules are unchanged).
W.add{entity=6002,type=W.AVATAR,unit=7102,health=10}
local other={call_id='x#1',definition='x',n=1,player={peer=THEM}}
mpm.mark_call(other)
assert(instances.associate(6002,other,'pelican'))
r=in_update(function()return own.credit_to_player(6002,me)end)
assert(r.applied==false and r.reason:find('OTHER_PLAYER',1,true),tostring(r.reason))
-- Not the local player: refused before anything.
r=in_update(function()return own.credit_to_player(6001,{peer=THEM,is_local=false})end)
assert(r.applied==false and r.reason:find('NOT_LOCAL_PLAYER',1,true))
return 'ok'
"""), b'ok')


if __name__ == '__main__':
    unittest.main()
