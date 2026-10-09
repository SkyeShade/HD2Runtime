"""Custom stratagems with custom multiplayer ENABLED, end to end with the example mods on the offline world of
tests/test_custom_stratagem_flow.py (the custom panel, the saved loadout, the mission record and HUD, the beacons), a
two-member lobby (tests/event_world_fixture.lua W.lobby) whose other member runs a compatible Runtime:
  * the live crash (custom_stratagems.lua:823, 'attempt to index local mine'): both peers publish -,-,-,-, both are
    enabled, then this player picks three custom stratagems; every Runtime step allocates from a view whose table holds
    this machine's CURRENT picks, every pick is READY, and the custom stratagem loop never dies;
  * the host with custom multiplayer enabled: Gas Barrage, Pelican CAS and Gas EAT reach their host execution paths
    (converted, presented, called, their beacons changed: the Gas Barrage's to the 120mm's own native barrage since its
    0.1.7 data form), never the token's native behaviour."""
import unittest

import test_custom_stratagem_flow as flow

MP = r"""
local custom=require('hd2runtime/runtime/custom_stratagems')
local channel=require('hd2runtime/runtime/peer_channel');channel.reset_for_tests()
local sync=require('hd2runtime/runtime/custom_mp_sync');sync.reset_for_tests()
local VERSION=require('hd2runtime/domains/metadata').version
local ME,THEM='1111222233334444','5555666677778888'
local function remote(seq,slots)
    W.lobby_values[THEM]=('hd2rt/1;%s;%s;%d;%s'):format(VERSION,custom.registry_hash(),seq,slots)
end
local function lobby(host)
    W.players({{peer=ME,avatar=100},{peer=THEM}},ME)
    W.lobby({members={ME,THEM},host=host or ME})
end
local function rejected()return count('scheduler rejected')end
"""


class CustomMultiplayerFlowTests(unittest.TestCase):
    def mp(self, body):
        flow.CustomStratagemFlowTests.lua(self, MP + body, carriers=flow.EAT_CARRIERS)

    def test_picks_changing_after_both_peers_are_enabled_never_kill_the_loop(self):
        self.mp(r"""
rawset(_G,'ModOptionsMenu',MENU)
examples()
lobby()
remote(1,'-,-,-,-')
tick(40)
ship({})
tick(120)
assert(count('custom multiplayer ENABLED')==1,lines('CUSTOM MP'))
-- This player picks Pelican CAS (slot 0), Gas Barrage (slot 1) and Gas EAT (slot 2); the other player changes too.
select_into(0)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',1);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F7')
tick(30)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',2);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F6');press('F7')
tick(30)
native_append(22)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
local V=require('hd2runtime/runtime/stratagem_selector').virtual_slots()
assert(V.slots[0].definition=='pelican_close_air_support'and V.slots[1].definition=='orbital_gas_barrage'
    and V.slots[2].definition=='eat17_gas',require('hd2runtime/runtime/stratagem_selector').slots_text(V))
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=PRECISION_ID},{id=ID22}})
remote(2,'orbital_gas_barrage,eat17_gas,-,-')
tick(120)
assert(rejected()==0,lines('scheduler rejected'))
-- The local peer resolves in the table with its CURRENT picks; every pick is READY from the synced allocation.
local v=sync.view()
assert(v.status=='enabled'and v.table[ME][0]=='pelican_close_air_support'and v.table[ME][2]=='eat17_gas'
    and v.table[THEM][0]=='orbital_gas_barrage',sync.slots_text(v.table[ME]))
for _,id in ipairs({'pelican_close_air_support','orbital_gas_barrage','eat17_gas'})do
    assert(count('PRE-MISSION ('..id..'): READY')>=1,lines('PRE-MISSION'))
end
assert(count('CUSTOM MP CARRIERS (aboard the ship, preview')>=1,lines('CUSTOM MP'))
-- More changes on both sides before the next allowed post: the loop survives each, the newest state wins.
remote(3,'-,-,-,-')
tick(20)
assert(rejected()==0 and sync.view().table[THEM][0]==false)
return 'ok'
""")

    def test_a_custom_last_pick_never_publishes_a_transient_all_vanilla_state(self):
        # Live r4: with the LAST selected stratagem a custom one, the published picks went -,-,-,- (the picks were
        # rebuilt from the saved loadout, which the game writes only when the loadout screen is left), then back.
        self.mp(r"""
rawset(_G,'ModOptionsMenu',MENU)
examples()
lobby()
remote(1,'-,-,-,-')
tick(40)
ship({})
tick(120)
assert(count('custom multiplayer ENABLED')==1,lines('CUSTOM MP'))
-- Every state this machine hands to the channel, in order.
local handed={}
local real=sync.publish
sync.publish=function(spec)
    local r=real(spec)
    if r~=nil then handed[#handed+1]=sync.slots_text(sync.mine().slots)end
    return r
end
local function last()return sync.slots_text(sync.mine().slots)end
-- Three custom picks; the last selected item is a custom one (no native pick after it). The saved loadout is never
-- updated while the screen is open (the game saves it when the screen is left).
select_into(0)
SCREEN.set('selecting',false);tick(2)
assert(last()=='pelican_close_air_support,-,-,-',last())
SCREEN.set('editedSlot',1);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F7')
tick(30)
assert(last()=='pelican_close_air_support,orbital_gas_barrage,-,-',last())
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',2);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F6');press('F7')
tick(30)
-- Right after the last (custom) pick: the three picks, before the selector even closes.
local want='pelican_close_air_support,orbital_gas_barrage,eat17_gas,-'
assert(last()==want,last())
-- The selector closes, the panel record repaints, the screen closes: the save still lags.
SCREEN.set('selecting',false);tick(8)
assert(last()==want,last())
SCREEN.close();tick(2)
assert(last()==want,'the screen closed with the save lagging: '..last())
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=PRECISION_ID}})
tick(40)
-- Never a transient all-vanilla state once a custom slot existed; every state handed on is a prefix of the picks.
for k,text in ipairs(handed)do
    assert(text~='-,-,-,-','state '..k..' of '..#handed..' was all vanilla: '..table.concat(handed,' | '))
end
assert(handed[#handed]==want,table.concat(handed,' | '))
assert(sync.mine().value and sync.mine().value:find(want,1,true),tostring(sync.mine().value))
assert(count('PICKS: the saved loadout')==0,lines('PICKS'))
-- A POSITIVE contradiction (the screen closed, the save settled with another stratagem in a custom slot for longer
-- than M.PICK_CONTRADICTION s) counts those slots as vanilla, once logged; the virtual slots themselves are kept.
W.saved_loadout({{id=PRECISION_ID},{id=ID22},{id=PRECISION_ID}})
tick(2)
assert(last()==want,'contradicted for less than '..custom.PICK_CONTRADICTION..' s: '..last())
tick(80)
assert(last()=='-,-,-,-'and count('PICKS: the saved loadout')==1,last()..' | '..lines('PICKS'))
assert(require('hd2runtime/runtime/stratagem_selector').virtual_slots()~=nil,'the virtual slots are never dropped here')
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=PRECISION_ID}})
tick(8)
assert(last()==want and count('PICKS: the saved loadout matches the virtual slots again')==1,last())
assert(rejected()==0)
return 'ok'
""")


HOST = r"""
rawset(_G,'ModOptionsMenu',MENU)
examples()
lobby()
remote(1,'orbital_gas_barrage,-,-,-')
tick(40)
ship({})
tick(4)
-- This host picks Pelican CAS (slot 0), Gas Barrage (slot 1) and Gas EAT (slot 2), then one native stratagem.
select_into(0)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',1);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F7')
tick(30)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',2);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F6');press('F7')
tick(30)
native_append(22)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=PRECISION_ID},{id=ID22}})
tick(120)
for _,id in ipairs({'pelican_close_air_support','orbital_gas_barrage','eat17_gas'})do
    assert(count('PRE-MISSION ('..id..'): READY')>=1,lines('PRE-MISSION'))
end
-- MISSION, the host: this machine's record (three tokens, a native) and the other player's (its custom Gas Barrage
-- slot holds the token; a native pick).
mission({host=true})
lobby(ME)
local record,hud=mission_record({118,118,118,22})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
local R=require('hd2runtime/domains/stratagem_slots').record
local other=h.record+R.stride
W.write(other,W.u32(0x77778888)..W.u32(0x55556666))
for k,e in ipairs({{124,1},{33,1},{118,0},{130,0},{41,1}})do
    local at=other+R.state+R.entries+(k-1)*R.entryStride
    W.write(at,W.u32(e[1]));W.write(at+4,W.u32(4294967295));W.write(at+9,string.char(e[2]))
end
W.write(other+R.state+R.entryCount,W.u32(5))
W.write(h.record+R.count,W.u32(2))
live_cooldowns(h,#record)
CT.player(0,0,0)
"""


class CustomMultiplayerHostTests(unittest.TestCase):
    def mp(self, body):
        flow.CustomStratagemFlowTests.lua(self, MP + body, carriers=flow.EAT_CARRIERS)

    def test_the_host_runs_gas_barrage_pelican_cas_and_gas_eat_exactly_as_before(self):
        self.mp(HOST + r"""
local barrages={}
require('hd2runtime/runtime/bombardment_executor').start=function(spec,callback)
    barrages[#barrages+1]=spec;return {status='active',cancel=function()end}
end
tick(160)
assert(rejected()==0 and count('STEP FAILED')==0 and count('SETUP REFUSED')==0,table.concat(logged,' | '))
assert(count('CUSTOM MP AGREEMENT (mission start): this machine is the session host')==1,lines('CUSTOM MP'))
local I=custom.internals_for_tests()
local M=I.mission()
assert(M.mp and M.mp.state=='running'and M.client==false,tostring(M.mp and M.mp.state))
local by={}
for _,item in ipairs(M.queue)do by[item.definition.id]=item end
for _,id in ipairs({'pelican_close_air_support','orbital_gas_barrage','eat17_gas'})do
    assert(by[id]and by[id].state=='ready'and by[id].client==false,id..': '..tostring(by[id]and by[id].state))
    assert(count('MISSION ('..id..'): READY TO CALL: loadout slot')==1,lines('MISSION'))
end
-- Each slot holds its own carrier (the token converted), the native pick untouched.
local function entry(i)return b.u32(W.read(h.record+0x38+0x188+i*0x30,4),0)end
local P,G,E=by.pelican_close_air_support.assignment,by.orbital_gas_barrage.assignment,by.eat17_gas.assignment
assert(entry(2)==P.type and entry(3)==G.type and entry(4)==E.type and entry(5)==22,
    ('converted: %d %d %d %d'):format(entry(2),entry(3),entry(4),entry(5)))
assert(P.type~=118 and G.type~=118 and E.type~=118,'never the token')
-- Calling each: its beacon changed in its first update exactly as on a solo host (never the native Precision Strike).
local C0=165760761
BOMB.set_clock(C0)
CT.beacon(0,7001,G.type,8,3,40,30,2);tick()
CT.beacon(1,7002,P.type,8,3,-20,10,1);tick()
CT.beacon(2,7003,E.type,8,3,5,5,0);tick()
assert(count('orbital_gas_barrage#1: beacon 7001 delivery '..G.carrier..' -> Orbital 120mm HE Barrage in its first '
    ..'update (1 write, verified true)')==1,lines('#1'))
assert(count('pelican_close_air_support#1: beacon 7002 delivery '..P.carrier..' -> none in its first update')==1,
    lines('#1'))
assert(count('eat17_gas#1: beacon 7003 delivery '..E.carrier..' -> EAT-17 Expendable Anti-Tank in its first update')==1,
    lines('#1'))
assert(CT.type_at(0)==136 and CT.type_at(1)==0 and CT.type_at(2)==147,'the deliveries: the 120mm\'s own barrage (Gas '
    ..'Barrage, native), none (Pelican CAS: the Runtime spawns it), the EAT-17 (Gas EAT)')
-- No call ever took the client proof path.
for _,c in ipairs(M.calls)do assert(c.client==false,c.call_id)end
assert(not require('hd2runtime/runtime/multiplayer').client_proof())
return 'ok'
""")

    def test_a_failed_setup_refuses_loudly_and_never_converts_and_the_loop_survives(self):
        self.mp(HOST + r"""
-- The synced allocation fails (an exception inside the mission setup).
local A=require('hd2runtime/runtime/carrier_allocator')
local original=A.allocate_lobby
local broken=true
A.allocate_lobby=function(...)if broken then error('allocator exploded')end;return original(...)end
tick(160)
assert(rejected()==0,'the scheduler never cancels the loop')
assert(count('STEP FAILED (a custom stratagem step):')==1 and count('allocator exploded')>=1,lines('STEP FAILED'))
-- Every custom slot of this machine is named, loudly; none converted (they stay the token, called natively).
for _,id in ipairs({'pelican_close_air_support','orbital_gas_barrage','eat17_gas'})do
    assert(count('CUSTOM MP SETUP REFUSED: loadout slot')>=1 and count('('..id..') is UNAVAILABLE in this mission')==1,
        lines('SETUP REFUSED'))
end
local function entry(i)return b.u32(W.read(h.record+0x38+0x188+i*0x30,4),0)end
assert(entry(2)==118 and entry(3)==118 and entry(4)==118,'a refused slot was converted')
assert(count('READY TO CALL')==0)
-- The loop is alive: the next steps run (the mission's end restores what it must, the ship step comes back).
broken=false
end_mission(h)
tick(40)
assert(rejected()==0 and count('STEP FAILED (a custom stratagem step):')==1)
return 'ok'
""")


class IncompatibleRegistryTests(unittest.TestCase):
    """0.30 RELEASE BLOCKER (live r7 log: theirs registry hash 79C3E713, mine 42944695): a lobby member running another
    custom stratagem registry disables custom stratagems LOBBY-WIDE and fails closed: no carrier, no conversion, no custom
    call, no provenance; every custom tile unavailable with the reason; this machine's custom slots kept but LOCKED in the
    mission (their token, Orbital Precision Strike, is never called); vanilla gameplay untouched."""

    def mp(self, body):
        flow.CustomStratagemFlowTests.lua(self, MP + body, carriers=flow.EAT_CARRIERS)

    SETUP = r"""
local notices={}
custom.hooks.alert=function()return {post=function(a)
    local t={a.title..' '..a.tag}
    for _,i in ipairs(a.items)do t[#t+1]=i.line;if i.fix then t[#t+1]=i.fix end end
    notices[#notices+1]=table.concat(t,' | ');return true end,clear=function()end}end
local function other_registry(seq,slots)
    W.lobby_values[THEM]=('hd2rt/1;%s;%s;%d;%s'):format(VERSION,'79C3E713',seq,slots)
end
rawset(_G,'ModOptionsMenu',MENU)
examples()
lobby()
remote(1,'-,-,-,-')
tick(40)
ship({})
tick(120)
assert(count('custom multiplayer ENABLED')==1,lines('CUSTOM MP'))
-- This player picks Pelican CAS (slot 0) and Gas Barrage (slot 1) while the lobby is compatible.
select_into(0)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',1);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F7')
tick(30)
native_append(22)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=ID22}})
tick(40)
-- The other player's Runtime now runs another custom stratagem registry.
other_registry(2,'-,-,-,-')
tick(60)
"""

    def test_aboard_the_ship_every_custom_stratagem_is_unavailable_and_nothing_is_allocated(self):
        self.mp(self.SETUP + r"""
local I=custom.internals_for_tests()
assert(count('custom multiplayer UNAVAILABLE')>=1 and count('runtime registry')==0,lines('CUSTOM MP STATE'))
assert(count('SHIP: CUSTOM STRATAGEMS DISABLED: incompatible custom-stratagem mods detected ('..THEM..': registry hash '
    ..'differs: theirs 79C3E713')==1,lines('SHIP'))
for _,id in ipairs({'pelican_close_air_support','orbital_gas_barrage','eat17_gas'})do
    assert(count('AVAILABILITY ('..id..'): UNAVAILABLE: CUSTOM STRATAGEMS DISABLED')==1,lines('AVAILABILITY'))
    assert(custom.unavailable(id):find('All players must use the same custom stratagems and versions',1,true))
end
assert(I.ship().alloc==nil and count('CARRIER BLOCKS')==0,'no carrier allocated, nothing blocked')
assert(#notices>=1 and notices[1]=='Custom stratagems Disabled | Incompatible custom-stratagem mods detected in the '
    ..'lobby. | All players must use the same custom stratagems and versions.',tostring(notices[1]))
-- The selected slots are kept (unpicking would leave a plain, callable token).
local V=require('hd2runtime/runtime/stratagem_selector').virtual_slots()
assert(V and V.slots[0].definition=='pelican_close_air_support'and V.slots[1].definition=='orbital_gas_barrage')
-- (The panel reads exactly this reason: its tile warns and a pick is refused, nothing written; test_custom_stratagem_
-- expendable ExpendablePanelTests covers that path.)
-- The other player installs the same mods again: enabled again.
remote(3,'-,-,-,-')
tick(80)
assert(count('SHIP: custom stratagems ENABLED again')==1 and custom.unavailable('pelican_close_air_support')==nil,
    lines('SHIP'))
return 'ok'
""")

    def mission_lines(self, host):
        return self.SETUP + (r"""
mission({host=%s})
lobby(%s)
local record,hud=mission_record({118,118,22,118})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
local before=W.read(h.record+0x38+0x188+5*0x30,0x30)
tick(160)
local I=custom.internals_for_tests()
local M=I.mission()
local function entry_type(i)return b.u32(W.read(h.record+0x38+0x188+i*0x30,4),0)end
local function entry_end(i)local raw=W.read(h.record+0x38+0x188+i*0x30+0x18,8);return b.u32(raw,0)+b.u32(raw,4)*4294967296 end
assert(count('MISSION: CUSTOM STRATAGEMS DISABLED')==1,lines('MISSION'))
-- Nothing custom: no allocation, no frozen map, no conversion, no beacon watch, no client proof.
assert(M.allocation==nil and M.carrier_types==nil and M.watch==nil and#M.queue==0,'nothing custom runs')
assert(count('FROZEN CARRIER MAP')==0 and count('stratagem slot CONVERTED')==0 and count('READY TO CALL')==0)
assert(entry_type(2)==118 and entry_type(3)==118,'the custom slots still hold the token')
-- Both custom slots' token entries are LOCKED (their end far above the game clock); the native picks untouched.
assert(count('CUSTOM STRATAGEM LOCKED: loadout slot 0 (pelican_close_air_support)')==1
    and count('CUSTOM STRATAGEM LOCKED: loadout slot 1 (orbital_gas_barrage)')==1,lines('LOCK'))
local clock=require('hd2runtime/runtime/slot_cooldown').clock(world_module.open())
assert(entry_end(2)>clock+3000*1000000 and entry_end(3)>clock+3000*1000000,'locked for the mission')
assert(W.read(h.record+0x38+0x188+5*0x30,0x30)==before,'the natively picked Orbital Precision Strike is never locked')
assert(count('LOCK FAILED')==0 and rejected()==0,lines('LOCK FAILED'))
return 'ok'
""" % ('true' if host else 'false', 'ME' if host else 'THEM'))

    def test_the_host_runs_nothing_custom_and_locks_its_custom_slots(self):
        self.mp(self.mission_lines(True))

    def test_a_client_runs_nothing_custom_and_locks_its_custom_slots(self):
        self.mp(self.mission_lines(False))


class LifecycleTests(unittest.TestCase):
    """0.30 lifecycle: ship -> mission -> ship. Mission-scoped state (the frozen carrier map and snapshot, evidence, calls,
    item and barrage provenance) ends with the mission; the custom slots come back only through the explicit ship
    loadout state (the saved loadout still holding the launched order); peers read fresh ship state afterwards."""

    def mp(self, body):
        flow.CustomStratagemFlowTests.lua(self, MP + body, carriers=flow.EAT_CARRIERS)

    def test_ship_mission_ship_resets_mission_state_reconciles_and_republishes_and_a_second_mission_is_fresh(self):
        self.mp(HOST + r"""
tick(160)
local I=custom.internals_for_tests()
assert(I.mission().carrier_types~=nil and count('SHIP LOADOUT (mission entry): custom slots ')==1,lines('SHIP LOADOUT'))
local mp_items=require('hd2runtime/runtime/custom_mp_items')
local evidence=require('hd2runtime/runtime/custom_mp_evidence')
local calls=require('hd2runtime/runtime/custom_mp_calls')
evidence.observe(4444,{id='pelican_close_air_support',peer=THEM,source='ball'},1)
local before=sync.mine()
local seq_before,slots_before=before.seq,sync.slots_text(before.slots)
-- Every state this machine hands to the channel from now on.
local handed={}
local real=sync.publish
sync.publish=function(spec)
    local r=real(spec)
    if r~=nil then handed[#handed+1]={seq=sync.mine().seq,slots=sync.slots_text(sync.mine().slots)}end
    return r
end
-- The mission ends (the same persistent lobby).
end_mission(h)
tick(2)
assert(I.mission().carrier_types==nil and I.mission().calls[1]==nil,'the frozen map and the calls ended with it')
assert(#mp_items.status().tracked==0 and#evidence.list(10)==0 and next(calls.status().handled)==nil,'provenance ended')
assert(count('virtual slots cleared: the mission ended')==1,lines('virtual slots'))
assert(#handed==0,'nothing new published before the reconciliation: '..#handed)
-- The teammate's pre-mission state is not used until it posts after the mission.
tick(8)
assert(sync.view().status=='waiting'and sync.view().reason:find('its state after the mission',1,true),
    tostring(sync.view().reason))
tick(20)
-- Reconciled (the saved loadout is the launched one): the slots come back; ONE post, a fresh seq, even unchanged.
assert(count('SHIP LOADOUT RECONCILED (back aboard the ship): custom slots ')==1 and count('restored (the saved loadout '
    ..'is the one they were launched with)')==1,lines('SHIP LOADOUT'))
local V=require('hd2runtime/runtime/stratagem_selector').virtual_slots()
assert(V and V.slots[0].definition=='pelican_close_air_support',tostring(V))
assert(#handed==1 and handed[1].seq==seq_before+1 and handed[1].slots==slots_before,#handed..' '..tostring(handed[1]
    and handed[1].slots))
-- The teammate posts its post-mission state: enabled again.
remote(9,'orbital_gas_barrage,-,-,-')
tick(20)
assert(sync.view().status=='enabled',tostring(sync.view().reason))
-- A second mission WITHOUT editing: a fresh snapshot, the frozen map again, the slots converted again.
mission({host=true})
lobby(ME)
local record2,hud2=mission_record({118,118,118,22})
local h2=W.stratagem_hud({peer=LOCAL,slots=hud2,record=record2})
-- The other player's record in this mission too (as in the first one).
local R2=require('hd2runtime/domains/stratagem_slots').record
local other2=h2.record+R2.stride
W.write(other2,W.u32(0x77778888)..W.u32(0x55556666))
for k,e in ipairs({{124,1},{33,1},{118,0},{130,0},{41,1}})do
    local at=other2+R2.state+R2.entries+(k-1)*R2.entryStride
    W.write(at,W.u32(e[1]));W.write(at+4,W.u32(4294967295));W.write(at+9,string.char(e[2]))
end
W.write(other2+R2.state+R2.entryCount,W.u32(5))
W.write(h2.record+R2.count,W.u32(2))
live_cooldowns(h2,#record2)
tick(160)
assert(count('CUSTOM MP SNAPSHOT (mission start, frozen for the setup)')==2 and count('FROZEN CARRIER MAP')==2,
    lines('SNAPSHOT'))
assert(count('MISSION (pelican_close_air_support): READY TO CALL: loadout slot')==2,lines('READY TO CALL'))
assert(rejected()==0 and count('STEP FAILED')==0,lines('STEP FAILED'))
return 'ok'
""")

    def test_a_loadout_changed_during_the_mission_is_never_guessed_back(self):
        self.mp(HOST + r"""
tick(160)
end_mission(h)
-- Back aboard the ship the saved loadout is not the launched one (the game, or the player elsewhere, changed it).
W.saved_loadout({{id=PRECISION_ID},{id=ID22},{id=PRECISION_ID}})
tick(20)
assert(count('SHIP LOADOUT RECONCILED (back aboard the ship): custom slots ')==1 and count('NOT restored: the saved '
    ..'loadout is')==1,lines('SHIP LOADOUT'))
assert(require('hd2runtime/runtime/stratagem_selector').virtual_slots()==nil)
assert(sync.slots_text(sync.mine().slots)=='-,-,-,-',sync.slots_text(sync.mine().slots))
return 'ok'
""")

    def test_another_lobby_forgets_every_member_and_a_reconnecting_peer_is_read_afresh(self):
        self.mp(r"""
rawset(_G,'ModOptionsMenu',MENU)
examples()
lobby()
remote(7,'orbital_gas_barrage,-,-,-')
tick(40)
ship({})
tick(40)
assert(sync.view().status=='enabled'and sync.view().table[THEM][0]=='orbital_gas_barrage')
-- The same player in ANOTHER lobby, its Runtime restarted (seq 1): read afresh, never "stale".
W.players({{peer=ME,avatar=100},{peer=THEM}},ME)
W.lobby({members={ME,THEM},host=ME,id='cv2:another'})
remote(1,'-,eat17_gas,-,-')
tick(20)
assert(count('CUSTOM MP: another lobby')==1 and count('a stale value')==0,lines('CUSTOM MP'))
assert(sync.view().table[THEM][1]=='eat17_gas',sync.slots_text(sync.view().table[THEM]))
-- It leaves and comes back (host migration / reconnect): read afresh too.
W.lobby({members={ME},host=ME,id='cv2:another'})
tick(24)
W.lobby({members={ME,THEM},host=THEM,id='cv2:another'})
remote(1,'-,-,eat17_gas,-')
tick(20)
assert(sync.view().table[THEM][2]=='eat17_gas'and sync.view().host_peer==THEM,sync.slots_text(sync.view().table[THEM]))
return 'ok'
""")


class ReadinessTests(unittest.TestCase):
    """0.30.2: aboard the ship, what will make the selected custom stratagems fail at the launch is predicted from the
    mission start's own rules and shown on screen with how to fix it (the safety notice panel), again every minute,
    and once more at the launch. Nothing is written."""

    def mp(self, body):
        flow.CustomStratagemFlowTests.lua(self, MP + body, carriers=flow.EAT_CARRIERS)

    def test_predicted_failures_are_shown_with_a_fix(self):
        self.mp(r"""
local notices,cleared={},{}
custom.hooks.alert=function()return {post=function(a)
    local t={a.severity,a.tag}
    for _,i in ipairs(a.items)do t[#t+1]=i.line;t[#t+1]=tostring(i.fix)end
    t[#t+1]=tostring(a.footer)
    notices[#notices+1]=table.concat(t,' | ');return true end,clear=function(k)cleared[#cleared+1]=k end}end
rawset(_G,'ModOptionsMenu',MENU)
examples()
local wm=require('hd2runtime/runtime/event_world')
local sel=require('hd2runtime/runtime/stratagem_selector')
local state,host,players='Ship',false,3
wm.game_state=function()return {name=state,host=host}end
wm.players=function()local t={};for i=1,players do t[i]={peer='P'..i}end;return t end
sel.virtual_slots=function()return {slots={[0]={definition='pelican_close_air_support',carrier=true,token=1}}}end
custom.hooks.stratagem_table=function()return true end
custom.reset_readiness_for_tests()
local world={runtime={}}
local writes=#(W.runtime.writes or{})
-- A client with a player without HD2Runtime: the launch would lock the custom slots.
local v={status='unavailable',peers={A={state='missing'},B={state='compatible'}}}
custom.readiness_step(world,v)
assert(#notices==1 and notices[1]:find('warn | Check before launch | 1 player without HD2Runtime: your custom slots '
    ..'will be locked. | Fix: everyone needs the same custom stratagem mods.',1,true),notices[1])
assert(count('READINESS: 1 problem: 1 player without HD2Runtime')==1)
custom.readiness_step(world,v)
assert(#notices==1,'the same problem is not shown again within a minute')
-- At the launch: shown once more, as a failure.
state='PrepareMission'
custom.readiness_step(world,v)
custom.readiness_step(world,v)
assert(#notices==2 and notices[2]:find('fail | Will fail',1,true)
    and notices[2]:find('Launching anyway: these slots stay locked for the mission.',1,true),notices[2])
-- The host runs its own customs: no multiplayer problem; a table another mod changed and a refused carrier are.
state,host='Ship',true
custom.reset_readiness_for_tests()
custom.hooks.stratagem_table=function()return 'hd2runtime/core/stratagem.lua:12: payload list pointer outside/ambiguous in owning group'end
custom.internals_for_tests().ship().status.pelican_close_air_support='NOT READY: no free member of its carrier group'
local problems=custom.readiness(world,v)
assert(#problems==2,#problems)
assert(problems[1].line:find(': no free member of its carrier group',1,true)
    and problems[1].advice=='Fix: free its carrier or pick another custom stratagem.')
assert(problems[2].line=='Another mod changed the stratagem data: custom names/looks will fail.')
custom.readiness_step(world,v)
-- Every problem is on the card (it lists three and counts the rest), each with its fix.
assert(notices[#notices]:find('no free member of its carrier group | Fix: free its carrier or pick another custom '
    ..'stratagem. | Another mod changed the stratagem data: custom names/looks will fail. | Fix: disable mods that '
    ..'change stratagems or hellpods, then restart.',1,true),notices[#notices])
-- Fixed: the problem card goes and a short READY confirmation replaces it. (The stratagem table is read once per
-- selection: another mod's change stands until a restart.)
custom.hooks.stratagem_table=function()return true end
custom.reset_readiness_for_tests()
custom.readiness_step(world,v)
assert(notices[#notices]:find('warn | Check before launch | pelican_close_air_support: no free member',1,true),notices[#notices])
custom.internals_for_tests().ship().status.pelican_close_air_support='READY: carrier X'
local n=#notices
custom.readiness_step(world,{status='enabled',peers={}})
assert(cleared[#cleared]=='readiness'and#notices==n+1 and notices[#notices]:find('ok | Ready | The problem is fixed',1,
    true),notices[#notices])
assert(count('READINESS: the selected custom stratagems are ready again')==1)
-- Ready from the start: no card at all.
custom.reset_readiness_for_tests()
n=#notices
custom.readiness_step(world,{status='enabled',peers={}})
assert(#notices==n,'no notice when everything is ready')
assert(#(W.runtime.writes or{})==writes,'nothing written')
return 'ok'
""")


    def test_the_stratagem_table_is_read_once_while_no_runtime_presentation_is_applied(self):
        # 0.30.2-dev5 live: picking Orbital Gas Barrage solo showed "Another mod changed the stratagem data" at once,
        # because the read saw the Runtime's own presentation on its carrier. Now it waits for a clean moment.
        self.mp(r"""
local notices={}
custom.hooks.alert=function()return {post=function(a)notices[#notices+1]=a.items[1].line;return true end,
    clear=function()end}end
rawset(_G,'ModOptionsMenu',MENU)
examples()
local wm=require('hd2runtime/runtime/event_world')
local sel=require('hd2runtime/runtime/stratagem_selector')
wm.game_state=function()return {name='Ship',host=true}end
wm.players=function()return {{peer='P1'}}end
sel.virtual_slots=function()return {slots={[3]={definition='orbital_gas_barrage',carrier=true,token=1}}}end
custom.internals_for_tests().ship().status.orbital_gas_barrage='READY: carrier Orbital Gatling Barrage'
custom.reset_readiness_for_tests()
local reads,applied=0,true
custom.hooks.presentation_applied=function()return applied end
custom.hooks.stratagem_table=function()reads=reads+1;return 'hd2runtime/core/stratagem.lua:12: payload list pointer outside/ambiguous in owning group'end
local world={runtime={}}
custom.readiness_step(world,{status='enabled',peers={}})
assert(reads==0 and#notices==0,'no read and no warning while the Runtime presentation is applied')
-- A clean moment: read once; a real difference is shown and logged with its reason.
applied=false
custom.readiness_step(world,{status='enabled',peers={}})
assert(reads==1 and notices[#notices]=='Another mod changed the stratagem data: custom names/looks will fail.')
assert(count('READINESS: the stratagem table does not read as reviewed')==1)
applied=true
custom.readiness_step(world,{status='enabled',peers={}})
applied=false
custom.readiness_step(world,{status='enabled',peers={}})
assert(reads==1,'read once per session: '..reads)
return 'ok'
""")

    def test_a_yielding_read_finishes_and_a_failed_read_is_no_verdict(self):
        # 0.30.2 live (a busy update): the table read yielded inside a pcall ("attempt to yield across C-call
        # boundary") and was reported as another mod's change. The read runs in its own coroutine now, and only the
        # table's own shape errors (core/stratagem.lua) count as a change.
        self.mp(r"""
local notices={}
custom.hooks.alert=function()return {post=function(a)notices[#notices+1]=a.items[1].line;return true end,
    clear=function()end}end
rawset(_G,'ModOptionsMenu',MENU)
examples()
local wm=require('hd2runtime/runtime/event_world')
local sel=require('hd2runtime/runtime/stratagem_selector')
wm.game_state=function()return {name='Ship',host=true}end
wm.players=function()return {{peer='P1'}}end
sel.virtual_slots=function()return {slots={[3]={definition='orbital_gas_barrage',carrier=true,token=1}}}end
custom.internals_for_tests().ship().status.orbital_gas_barrage='READY: carrier Orbital Gatling Barrage'
custom.hooks.presentation_applied=function()return false end
-- The real hook over a capture that yields three times (a reader out of its time slice) and then succeeds.
local S=require('hd2runtime/core/stratagem')
local real=S.capture_all
local yields=0
S.capture_all=function()for _=1,3 do yields=yields+1;coroutine.yield()end;return {}end
assert(custom.hooks.stratagem_table({runtime={}})==true and yields==3,'a yielding read finishes')
S.capture_all=real
-- A read that fails for another reason: no card, logged once, tried again later.
custom.reset_readiness_for_tests()
local reads=0
custom.hooks.stratagem_table=function()reads=reads+1;return 'hd2runtime/runtime/reader.lua:29: memory query failed'end
local world={runtime={}}
custom.readiness_step(world,{status='enabled',peers={}})
custom.readiness_step(world,{status='enabled',peers={}})
assert(reads==1 and#notices==0,'no verdict and no card: '..reads..' '..#notices)
assert(count('READINESS: the stratagem table could not be read now')==1)
assert(count('does not read as reviewed')==0)
return 'ok'
""")

if __name__ == '__main__':
    unittest.main()
