"""The Pelican CAS with several players (runtime/custom_mp_calls.lua, runtime/custom_mp_pelican.lua,
runtime/pelican_weapon.lua mirror_configure / mirror_interval, runtime/projectile_impact.lua bind_credit;
research/docs/runtime-peer-messaging-F5FEE03DCFDB.md section 15):
  * a client requests its call from the session host with semantic state only (custom id, beacon network id, call
    sequence, loadout slot, carrier map hash); the host runs it once, only when its synced slot, the carrier map, a new
    sequence and its beacon's thrower agree, as that player's call (credit to that player), and publishes the Pelican's
    and its chin turret's network ids;
  * every other machine mirrors the chin gun's private presentation on its OWN copy of the turret (the copy's round,
    rate slot and casing, zero recoil, the spread, the shot interval held), never what the network writes (its current
    RPM, rounds, trigger, AI), and only on a network copy of a published turret;
  * the host credits each round of that turret to the requesting player (its own pool creditor, before its first
    step); a round credited to anyone else is never touched."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_gas_eat import IMPACT
import test_custom_mp_items as items
from test_custom_mp_mission import example_addon

MIRROR = r"""
local PM=require('hd2runtime/domains/peer_messaging').pelicanMirror
for _,pin in ipairs(PM.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local mpx=require('hd2runtime/runtime/multiplayer');mpx.reset_for_tests()
-- A client's copy of the host's Pelican and chin turret: their types in the entity map, the turret not created here.
local function client_copy()
    pworld()
    BOMB.set_clock(T0)
    tcount(0)
    scene()
    W.state(4,{host=false})          -- this machine is a client: the scene is its copy of the host's Pelican
    -- Their types (the payload world's component world is the bombardment object: the entity map is the fixture's own).
    local wm=require('hd2runtime/runtime/event_world')
    local entity_type=wm.entity_type
    wm.entity_type=function(w,e)
        if e==9501 then return PM.pelicanResource elseif e==8102 then return PM.chinResource end
        return entity_type(w,e)
    end
    W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(0))
    mpx.enable_client_proof(true)
    return world_module.open()
end
local SPEC={pelican=9501,round='standard',gatling=true,rate_factor=2,spread=100,recoil='zero',client=true}
local custom_pelican=require('hd2runtime/runtime/custom_mp_pelican')
local metrics=require('hd2runtime/runtime/metrics')
local PWX=TW.projectileWeapon
-- This machine's own instance records in a page-backed allocation (as the game's heap is; the fixture's own is half a
-- page). The turret is instance 0.
local function instances()
    local inst=W.alloc(0x1000)
    W.write(inst,W.read(PINST,0x800))
    W.write(PCOMP+PWX.instances,W.u64(inst))
    return inst
end
-- Its fire state as the game leaves it: entry (the replicated current RPM entry), cached (+0x64), interval (+0xC),
-- trigger (+1), firing (+0), shots (+0x3C).
local function set_fire(inst,o)
    local C=PM.cadence
    if o.entry then W.write(b.pointer(W.read(PCOMP+PWX.current,8),0)+PWX.currentRpm,f32(o.entry))end
    if o.cached then W.write(inst+PM.instanceCachedRpm,f32(o.cached))end
    if o.interval then W.write(inst+PM.instanceInterval,f32(o.interval))end
    if o.trigger then W.write(inst+C.trigger,string.char(o.trigger))end
    if o.firing then W.write(inst+C.firing,string.char(o.firing))end
    if o.shots then W.write(inst+C.shots,W.u32(o.shots))end
end
local function interval_of(inst)return b.value(W.read(inst+PM.instanceInterval,4),0,'f32')end
local function single(v)return b.value(b.encode(v,'f32'),0,'f32')end
local function entry_raw()return W.read(b.pointer(W.read(PCOMP+PWX.current,8),0),PWX.currentStride)end
-- The orchestrator's mirror of the published turret (runtime/custom_mp_pelican.lua), as the pelican handler binds it.
local GUN={behave_as='gatling_sentry',rate_multiplier=2,round='standard',spread=100,recoil=false}
local function mirror()
    return custom_pelican.mirror({turret=8102,pelican=9501,network=701,gun=GUN,label='m',client=true})
end
local function gone()
    local wm=require('hd2runtime/runtime/event_world')
    wm.entity_exists=function(w,e)if e==8102 then return false end return true end
end
"""


class MirrorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + MIRROR
            + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_a_client_mirrors_the_chin_gun_on_its_own_copy_only(self):
        self.check(r"""
local world=client_copy()
local before=pelicans.weapon_config(world,8102)
local mag=W.read(MGRECS,MG.stride)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.mirror_configure(world,8102,SPEC,'mirror')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
local w=pelicans.weapon_config(world,8102)
-- Its own copy: the round, the Gatling rate slot (x2), the casing; its own recoil and spread; nothing shared.
assert(w.copy and w.copy.projectileType==148 and r.projectile==148 and r.verify.recoil and r.verify.spread
    and r.verify.shared,tostring(w.copy and w.copy.projectileType))
assert(r.casing.applied,'the casing before its first local shot: '..tostring(r.casing.reason))
-- Never what the network writes: its current RPM entry (the host's seed), its rounds and chamber.
assert(w.currentRpm==before.currentRpm and W.read(MGRECS,MG.stride)==mag,'a networked field was written')
assert(n('PELICAN WEAPON MIRROR APPLIED (mirror): chin turret 8102 (a network copy here): its own copy names projectile 148')
    ==1,table.concat(logged,' | '))
-- Again: refused (configured already), nothing more written.
local w0=#W.runtime.writes
assert(select(2,in_update(function()return weapon.mirror_configure(world,8102,SPEC,'mirror')end))=='ALREADY_CONFIGURED'
    and#W.runtime.writes==w0)
""")

    def test_the_interval_follows_the_gatling_rate_while_the_hosts_seed_stands(self):
        self.check(r"""
local world=client_copy()
assert(in_update(function()return weapon.mirror_configure(world,8102,SPEC,'mirror')end))
local inst=instances()
local rpm=single(weapon.FROZEN.rpm*2)
-- The host's seed (300) stands and the game has cached it: held at 60 / (the Gatling rate x 2), read back.
set_fire(inst,{cached=300})
local e=in_update(function()return weapon.mirror_interval(world,8102,2)end)
assert(e.kind=='held'and e.basis=='seed'and e.factor==1 and e.rpm==rpm and interval_of(inst)==single(60/rpm),
    tostring(e.kind)..' '..tostring(e.code)..' '..tostring(e.reason))
-- Held: nothing more to write.
local w0=#W.runtime.writes
assert(in_update(function()return weapon.mirror_interval(world,8102,2)end).kind=='steady'and#W.runtime.writes==w0)
-- The game is about to rewrite it (its cached copy differs): pending, nothing written this update.
set_fire(inst,{cached=250})
assert(in_update(function()return weapon.mirror_interval(world,8102,2)end).kind=='pending'and#W.runtime.writes==w0)
-- Neither the chin turret's seed nor this gun's Gatling rate (1600, the sentry's own): unknown, nothing written.
set_fire(inst,{entry=1600,cached=1600})
local u=in_update(function()return weapon.mirror_interval(world,8102,2)end)
assert(u.kind=='unknown'and u.code=='UNKNOWN_RATE'and#W.runtime.writes==w0,u.kind)
-- Under mission modifier 0x33 (the seed x 0.9): held at 60 / (the Gatling rate x 0.9 x 2).
set_fire(inst,{entry=270,cached=270})
local m=in_update(function()return weapon.mirror_interval(world,8102,2)end)
local r9=single(weapon.FROZEN.rpm*PE.rateSeed.factor*2)
assert(m.kind=='held'and m.basis=='seed'and m.rpm==r9 and interval_of(inst)==single(60/r9),m.kind)
-- Outside the Runtime update: refused.
assert(weapon.mirror_interval(world,8102,2).code=='NOT_GAME_THREAD')
""")

    def test_a_replicated_gatling_rate_is_held_and_the_cadence_is_sampled(self):
        # Regression (r4 live, 2026-10-05, "interval held 0 times"): a client whose replicated current RPM entry is the
        # host's Gatling rate, not the chin turret's seed, still gets its own cadence held, and says so (the periodic
        # samples need the diagnostics switch since 0.30 release hardening).
        self.check(r"""
require('hd2runtime/runtime/log').verbose(true)
local world=client_copy()
local inst=instances()
local rpm=single(weapon.FROZEN.rpm*2)
-- The host's Gatling rate x 2 replicated and cached; this copy's interval still its creation value (60 / 300).
set_fire(inst,{entry=rpm,cached=rpm,interval=0.2,trigger=1,firing=1,shots=0})
local m=mirror()
tick()                                       -- its own copy configured
assert(m.configured and n('chin gun MIRRORED')==1,table.concat(logged,' | '))
tick()                                       -- the cadence held
assert(m.counts.held==1 and interval_of(inst)==single(60/rpm),table.concat(logged,' | '))
assert(n('(3200 RPM, gatling x1) on this machine; held while its current RPM entry stands')==1,table.concat(logged,' | '))
assert(n('REMOTE CUSTOM PELICAN CADENCE: m: FIRST')==1
    and n('current RPM entry 3200.00 (the host\'s), cached 3200.00, interval 0.0188 s (expected 0.0188 s = 3200 RPM, '
    ..'gatling x1)')==1 and n('branch held (written over 0.2000 s)')==1,table.concat(logged,' | '))
-- Firing: a sample every 0.25 s with its own local shots (7 a 0.125 s update: 3360 RPM).
for k=1,8 do set_fire(inst,{shots=k*7});tick()end
assert(m.samples==5 and n('shots 14 (+14 in 0.25 s = 3360 RPM here)')==1 and n('branch steady')==4,
    m.samples..' | '..table.concat(logged,' | '))
-- The end: why it held, per branch.
gone();tick()
assert(n('REMOTE CUSTOM PELICAN: m: mirror ended (the chin turret is gone); interval held 9 times (written 1, already '
    ..'steady 8; not held: pending 0, unknown rate 0, refused 0); held on 9 of 9 updates')==1 and n('NEVER HELD')==0,
    table.concat(logged,' | '))
""")

    def test_the_live_r5_entry_299_96_is_the_seed_and_is_held(self):
        # Live r5 (2026-10-05, the client): current RPM entry 299.96, cached 299.96, interval 0.2000 s, the visible
        # cadence about 230..470 RPM. The r5 match (1e-4) called 299.96 neither the seed (300) nor the Gatling rate, so
        # nothing was held. Within the relative tolerance it is the seed: held at 60 / 3200.
        self.check(r"""
local world=client_copy()
local inst=instances()
local rpm=single(weapon.FROZEN.rpm*2)
set_fire(inst,{entry=299.96,cached=299.96,interval=single(60/299.96),trigger=1,firing=1,shots=0})
local m=mirror()
tick()
tick()
assert(m.counts.held==1 and m.counts.unknown==0 and interval_of(inst)==single(60/rpm),table.concat(logged,' | '))
local e=in_update(function()return weapon.mirror_interval(world,8102,2)end)
assert(e.kind=='steady'and e.basis=='seed'and e.factor==1,tostring(e.kind))
-- Without the diagnostics switch only the FIRST cadence sample is logged (release logging), whatever it samples.
require('hd2runtime/runtime/log').verbose(false)
set_fire(inst,{trigger=1,firing=1,shots=0})
for k=1,8 do set_fire(inst,{shots=k*7});tick()end
assert(n('REMOTE CUSTOM PELICAN CADENCE: ')==1 and m.samples>1,m.samples..' | '..table.concat(logged,' | '))
-- Still a different rate (outside 1 %) is never guessed.
set_fire(inst,{entry=310,cached=310})
assert(in_update(function()return weapon.mirror_interval(world,8102,2)end).kind=='unknown')
""")

    def test_the_end_line_says_why_it_never_held(self):
        self.check(r"""
local world=client_copy()
local inst=instances()
-- A replicated rate that is neither the seed nor this gun's Gatling rate: never written, and the end line says why.
set_fire(inst,{entry=1600,cached=1600})
local m=mirror()
for _=1,5 do tick()end
local w=#W.runtime.writes
assert(m.counts.unknown==4 and m.counts.held==0 and interval_of(inst)==single(60/300))
-- Not firing: one sample every 5 s.
assert(m.samples==1 and n('branch unknown UNKNOWN_RATE')==1,table.concat(logged,' | '))
gone();tick()
assert(#W.runtime.writes==w and n('interval held 0 times (written 0, already steady 0; not held: pending 0, unknown rate '
    ..'4, refused 0); NEVER HELD: its current RPM entry was never the chin turret\'s seed nor the Gatling rate (4 of 4 '
    ..'updates) last code UNKNOWN_RATE')==1,table.concat(logged,' | '))
""")

    def test_nothing_is_written_on_a_turret_created_here(self):
        self.check(r"""
local world=client_copy()
assert(in_update(function()return weapon.mirror_configure(world,8102,SPEC,'mirror')end))
local inst=instances()
set_fire(inst,{cached=300})
-- Now this machine's own turret (as on the host): refused, its records untouched.
W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(1))
local w0,before,entry=#W.runtime.writes,W.read(inst,0xA8),entry_raw()
local e=in_update(function()return weapon.mirror_interval(world,8102,2)end)
assert(e.kind=='refused'and e.code=='CREATED_HERE'and#W.runtime.writes==w0 and W.read(inst,0xA8)==before
    and entry_raw()==entry,tostring(e.code))
""")
        self.check(r"""
local world=client_copy()
local inst=instances()
set_fire(inst,{cached=300})
W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(1))       -- the host's own turret
local w0,calls,before=#W.runtime.writes,#GX.calls,W.read(inst,0xA8)
local m=mirror()
for _=1,4 do tick()end
-- Its configuration refuses it: no game call, no write, the mirror ends.
assert(m.status=='complete'and#GX.calls==calls and#W.runtime.writes==w0 and W.read(inst,0xA8)==before)
assert(n('mirror ended (refused: CREATED_HERE: this machine created that turret')==1,table.concat(logged,' | '))
""")

    def test_the_mirror_never_fires_or_calls_the_game(self):
        self.check(r"""
local world=client_copy()
local inst=instances()
set_fire(inst,{cached=300,trigger=1,firing=1,shots=3})
local m=mirror()
tick()                                       -- its own copy (the one game call: the copy routine)
assert(m.configured and#GX.calls==1 and GX.calls[1][1]=='copy',#GX.calls)
local calls,natives=#GX.calls,metrics.snapshot().counters['pelican_weapon.native_calls']
local w0,before,entry=#W.runtime.writes,W.read(inst,0xA8),entry_raw()
for _=1,24 do tick()end                       -- 3 s of updates and samples
-- No game call (no shot, no projectile, no fire event of its own), and one write: its own interval, once. Its cooldown,
-- trigger, firing, fire decision, shot count, cached RPM and current RPM entry are the game's.
assert(#GX.calls==calls and metrics.snapshot().counters['pelican_weapon.native_calls']==natives)
assert(#W.runtime.writes==w0+1 and W.runtime.writes[w0+1].address==inst+PM.instanceInterval,#W.runtime.writes-w0)
local after=W.read(inst,0xA8)
assert(after:sub(1,PM.instanceInterval)==before:sub(1,PM.instanceInterval)
    and after:sub(PM.instanceInterval+5)==before:sub(PM.instanceInterval+5) and entry_raw()==entry)
assert(m.counts.held==1 and m.counts.steady==23 and m.samples==12,m.samples)
""")

    def test_only_a_network_copy_of_a_published_turret_inside_the_proof(self):
        self.check(r"""
local world=client_copy()
local function refused(spec,code)
    local r,c,why=in_update(function()return weapon.mirror_configure(world,8102,spec,'mirror')end)
    assert(not r and c==code,code..' expected, got '..tostring(c)..' '..tostring(why))
end
-- The proof off on a client: refused.
mpx.enable_client_proof(false)
refused(SPEC,'NOT_HOST')
mpx.enable_client_proof(true)
-- Not the published Pelican, not attached to it, created here: refused, nothing written.
local w0=#W.runtime.writes
local s={};for k,v in pairs(SPEC)do s[k]=v end;s.pelican=8102
refused(s,'NOT_A_PELICAN')
W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(1))
refused(SPEC,'CREATED_HERE')
assert(#W.runtime.writes==w0)
-- Outside the Runtime update.
W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(0))
assert(select(2,weapon.mirror_configure(world,8102,SPEC,'mirror'))=='NOT_GAME_THREAD')
""")


CREDIT = r"""
local P1,P2='1111222233334444','5555666677778888'
"""


class CreditTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + IMPACT + CREDIT + body + "\nreturn 'ok'"), b'ok')

    def test_the_host_credits_each_round_to_the_requesting_player(self):
        self.check(r"""
iworld()
W.players({{peer=LOCAL_PEER,avatar=100},{peer=P2}},LOCAL_PEER)
local events={}
local binding,code,why=impacts.bind_credit({sources={5001},projectiles={132},credit_to=P2,label='Pelican credit',
    multiplayer=true},function(e)events[#events+1]=e end)
assert(binding,tostring(code)..' '..tostring(why))
tick()
local writes=#W.runtime.writes
local function creditor(hit)local raw=W.read(hit+H.creditor,8);return require('hd2runtime/runtime/event_world').peer_hex(
    b.u32(raw,0),b.u32(raw,4))end
-- Its rounds credited to the host (the game's own) or to nobody: credited to the requesting player, one write each.
local _,h1=fire(5001,{creditor=LOCAL_PEER});local _,h2=fire(5001,{creditor='0000000000000000'})
tick()
assert(creditor(h1)==P2 and creditor(h2)==P2 and#W.runtime.writes==writes+2,creditor(h1)..' '..creditor(h2))
assert(impact_of(h1)==376,'nothing else of the round changes')
assert(count('projectile impact CREDIT (Pelican credit): projectile 132 in pool slot')==1,table.concat(logged,' | '))
-- A round credited to anyone else is never touched; another source's never either.
local _,h3=fire(5001,{creditor='9999888877776666'});local _,h4=fire(5002,{creditor=LOCAL_PEER})
tick()
assert(creditor(h3)=='9999888877776666'and creditor(h4)==LOCAL_PEER and#W.runtime.writes==writes+2)
assert(count('CREDIT REFUSED (Pelican credit)')==1)
binding.cancel()
assert(count('CREDIT (Pelican credit): ended (cancelled): 2 rounds credited to '..P2)==1,table.concat(logged,' | '))
""")

    def test_the_credit_is_refused_off_the_host_or_for_a_non_player(self):
        self.check(r"""
iworld()
W.players({{peer=LOCAL_PEER,avatar=100},{peer=P2}},LOCAL_PEER)
local function refused(spec,code)
    local b_,c,why=impacts.bind_credit(spec)
    assert(not b_ and c==code,code..' expected, got '..tostring(c)..' '..tostring(why))
end
refused({sources={5001},projectiles={132},credit_to='7777777777777777',multiplayer=true},'NOT_A_PLAYER')
refused({sources={5001},projectiles={132},credit_to=LOCAL_PEER,multiplayer=true},'INVALID')
refused({sources={5001},projectiles={132},credit_to=P2},'NOT_SOLO')
W.state(4,{host=false});tick()
refused({sources={5001},projectiles={132},credit_to=P2,multiplayer=true},'NOT_HOST')
""")


class RequestTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        pelican, pelican_addon = example_addon('PelicanCasExample')
        eat, eat_addon = example_addon('GasEatExample')
        harness = items.HARNESS.replace(
            "assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()",
            "assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()\nassert(loadstring(PELICAN_ADDON,'@'..PELICAN_RESOURCE))()"
        ).replace(
            "selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17_gas',token=PRECISION,type=118}},\n"
            "    pairs={PRECISION,1}})",
            "selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17_gas',token=PRECISION,type=118},\n"
            "    [1]={definition='pelican_close_air_support',token=PRECISION,type=118}},pairs={PRECISION,PRECISION,1}})"
        ).replace(
            """        if d.id=='eat17_gas'then""",
            """        if d.id=='pelican_close_air_support'then
            a.assignments[d.id]={label='Pelican',carrier='Orbital Airburst Strike',stable_id=1560416221,type=83,
                family='orbital',owned=true}
        end
        if d.id=='eat17_gas'then""").replace(
            "        table={[me]={[0]='eat17_gas',[1]=false,[2]=false,[3]=false},[other]={[0]='eat17_gas',[1]=false,[2]=false,\n"
            "        [3]=false}},local_seq=1,local_posted=true,\n"
            "        peers={[other]={state='compatible',seq=1,slots={[0]='eat17_gas',[1]=false,[2]=false,[3]=false},items={}}}}",
            "        table={[me]={[0]='eat17_gas',[1]='pelican_close_air_support',[2]=false,[3]=false},[other]={[0]='eat17_gas',\n"
            "        [1]='pelican_close_air_support',[2]=false,[3]=false}},local_seq=1,local_posted=true,\n"
            "        peers={[other]={state='compatible',seq=1,slots={[0]='eat17_gas',[1]='pelican_close_air_support',[2]=false,\n"
            "        [3]=false},items={},calls={}}}}").replace(
            "    cmp.first_records=function()return {rec(me,{118,22}),rec(other,{118,41})}end",
            "    cmp.first_records=function()return {rec(me,{118,118,22}),rec(other,{118,118,41})}end")
        assert "PELICAN_ADDON,'@'" in harness and "calls={}}}}" in harness and "rec(me,{118,118,22})" in harness
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + IMPACT + 'local EAT_ADDON=' + lua_literal(eat_addon)
            + '\nlocal EAT_RESOURCE=' + lua_literal(eat) + '\nlocal PELICAN_ADDON=' + lua_literal(pelican_addon)
            + '\nlocal PELICAN_RESOURCE=' + lua_literal(pelican) + harness + r"""
local api=require('hd2runtime/api/pelican')
local SPAWNS={}
api.spawn=function(opts)SPAWNS[#SPAWNS+1]=opts;return {status='requested'}end
local mp_calls=require('hd2runtime/runtime/custom_mp_calls')
local beacons_module=require('hd2runtime/runtime/beacons')
beacons_module.position=function(world,entity)return {x=40,y=30,z=2}end
local function queue_of(M,id)for _,q in ipairs(M.queue)do if q.definition.id==id then return q end end end
""" + body + "\nreturn 'ok'"), b'ok')

    def test_a_client_requests_its_call_with_semantic_state_only(self):
        self.lua(r"""
local world,M=machine(P2,false)
local q=queue_of(M,'pelican_close_air_support')
assert(q and q.client==true,'the Pelican runs on a client as a request')
local d=custom.get('pelican_close_air_support')
local ctx=I.new_call(d,q.assignment,1)
ctx.beacon={entity=7201,network=4160}
I.pelican_call(ctx,d)
assert(#SPAWNS==0,'a client never spawns it')
local out=mp_calls.published(0)
assert(#out==1 and out[1].id=='pelican_close_air_support'and out[1].beacon==4160 and out[1].seq==1 and out[1].slot==1
    and out[1].carrier==M.mp.carrier_hash)
local text=P.encode({version='0.30.0-dev',registry='0A1B2C3D',seq=3,slots={'eat17_gas','pelican_close_air_support'},
    calls=out})
assert(text:find(';calls:pelican_close_air_support@4160#1=1:'..M.mp.carrier_hash,1,true),text)
assert(not text:find('275',1,true)and not text:find('rpm',1,true),'never a gun configuration')
assert(count('CUSTOM MP CALL REQUESTED: the session host spawns the Pelican for this call (call seq 1, loadout slot 1, '
    ..'beacon network id 4160')==1,table.concat(logged,' | '))
""")

    def test_the_host_runs_a_valid_request_once_for_that_player(self):
        self.lua(r"""
local world,M=machine(P1,true)
remote_call(8201,4160,P2,83,1)
local good={id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}
V.peers[P2].calls={good}
I.calls_step(world)
assert(#SPAWNS==1,'spawned once: '..#SPAWNS..' | '..table.concat(logged,' | '))
local o=SPAWNS[1]
assert(o.position.x==40 and o.call.remote==true and o.call.player_peer==P2 and o.credit_to.peer==P2
    and o.credit_to.is_local==false and mpm.call_allowed(o.call),'the call is that player\'s')
assert(o.gun and o.gun.round=='ap4'and o.hover==60,'its own definition\'s data')
assert(count('CUSTOM MP CALL REQUEST: peer '..P2..' asks the host to run custom pelican_close_air_support (call seq 1, '
    ..'loadout slot 1, beacon network id 4160): ACCEPTED')==1,table.concat(logged,' | '))
-- The same sequence again: never a second Pelican.
I.calls_step(world);I.calls_step(world)
assert(#SPAWNS==1)
-- The host publishes the Pelican's and its chin turret's network ids (from its spawn events).
W.add{entity=9501,type='75BE82ED8592A6B3',unit=0,health=1};W.register_entity(9501,'75BE82ED8592A6B3',0,4170)
W.network_id(4170,9501,40)
W.add{entity=8102,type='8365609B35EF6672',unit=0,health=1};W.register_entity(8102,'8365609B35EF6672',0,4171)
W.network_id(4171,8102,41)
o.on_event({kind='spawned',result={entity=9501}})
o.on_event({kind='gun_armed',turret=8102,projectile=275,round='ap4',rpm=3200,credit=true})
local out=mp_items.published(world)
assert(#out==1 and out[1].id=='pelican_close_air_support'and out[1].beacon==4160 and out[1].items[1]==4170
    and out[1].items[2]==4171,table.concat(logged,' | '))
-- Their provenance: the Pelican (vehicle) and its chin turret (its child).
local prov=require('hd2runtime/runtime/custom_provenance')
assert(prov.get(4170).role=='vehicle'and prov.get(4171).role=='turret'and prov.get(4171).parent_network_id==4170)
-- The host-run call's common shape: authority host, its caller the requesting player.
local cc=o.call.custom_call
assert(cc and cc.authority=='host'and cc.caller_peer==P2 and cc.slot==1 and cc.beacon_network==4160)
""")

    def test_a_client_request_survives_its_thrown_ball_and_beacon_copy(self):
        # Live r4: the client's CUSTOM MP CALL REQUESTED was published, but the host never ran it (no ACCEPTED, no HOST
        # CALL): the host checked what the game still held when the slower request arrived.
        self.lua(r"""
local world,M=machine(P1,true)
local S=require('hd2runtime/runtime/stratagem_slot_conversion')
S.records=function()return {rec(P1,{118,118,22}),rec(P2,{118,118,41})}end
-- P2's thrown ball while it lands: it names beacon network id 4160, P2's record entry 2 (loadout slot 1), the
-- carrier type 83 (Orbital Airburst Strike -> pelican_close_air_support in the frozen carrier map).
local BALLS={{index=0,type=83,owner=P2,entry=2,beacon_network=4160}}
call_ins.balls=function()return BALLS end
I.ball_scan(world);I.ball_scan(world)
assert(count('CUSTOM MP EVIDENCE: beacon network id 4160: peer '..P2..'\'s thrown ball (record entry 2, loadout slot 1), '
    ..'carrier Orbital Airburst Strike -> custom pelican_close_air_support by the frozen carrier map')==1,
    table.concat(logged,' | '))
-- Its beacon copy here (no state: another machine's), then the ball AND the beacon copy are gone.
local beacons_seen={[8201]={type=83}}
BR.beacons=function()return beacons_seen end
pods.beacon_network=function()return 4160 end
I.beacon_event({kind='created',beacon={entity=8201,type=83,landed=false,timing={}}})
BALLS={};beacons_seen={}
beacons_module.position=function()return nil end
tick(15)
-- 15 s later the request arrives (PlayFab): accepted from this machine's own cached observation; one Pelican, at the
-- beacon's observed position, for that player.
local good={id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}
V.peers[P2].calls={good}
I.calls_step(world)
assert(#SPAWNS==1,'spawned once: '..#SPAWNS..' | '..table.concat(logged,' | '))
assert(SPAWNS[1].position.x==40 and SPAWNS[1].call.player_peer==P2 and SPAWNS[1].credit_to.peer==P2)
assert(count('(call seq 1, loadout slot 1, beacon network id 4160): ACCEPTED (its synced slot, the carrier map hash, a '
    ..'new sequence and this machine\'s own observation agree: the beacon\'s carrier maps to pelican_close_air_support, its '
    ..'caller is the sender (the thrown ball), loadout slot 1')==1,table.concat(logged,' | '))
-- Replayed (the same sequence) and a new sequence naming the same beacon: never a second Pelican.
I.calls_step(world)
V.peers[P2].calls={good,{id='pelican_close_air_support',beacon=4160,seq=2,slot=1,carrier=M.mp.carrier_hash}}
I.calls_step(world);I.calls_step(world)
assert(#SPAWNS==1,#SPAWNS)
assert(count('(call seq 2, loadout slot 1, beacon network id 4160): REFUSED: a call already ran for that beacon (peer '
    ..P2..', call seq 1): one host call per beacon')==1,table.concat(logged,' | '))
""")

    def test_a_request_without_any_ball_is_validated_by_the_frozen_carrier_map(self):
        self.lua(r"""
local world,M=machine(P1,true)
-- No ball was ever read here; the beacon copy of the carrier was (the only other player selecting its id is P2).
local beacons_seen={[8201]={type=83}}
BR.beacons=function()return beacons_seen end
pods.beacon_network=function()return 4160 end
call_ins.thrower=function()return nil,'no thrown ball names that beacon (yet)'end
I.beacon_event({kind='created',beacon={entity=8201,type=83,landed=false,timing={}}})
V.peers[P2].calls={{id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}}
I.calls_step(world)
assert(#SPAWNS==1,table.concat(logged,' | '))
assert(count('its caller is the sender (derived from the frozen table: the only other player selecting it)')==1,
    table.concat(logged,' | '))
""")

    def test_evidence_older_than_its_window_never_validates_a_request(self):
        self.lua(r"""
local world,M=machine(P1,true)
remote_call(8201,4160,P2,83,1)
-- The request comes after the evidence window (45 s): this machine no longer vouches for that call.
local ev=require('hd2runtime/runtime/custom_mp_evidence')
for _=1,(ev.KEEP/custom.STEP)+8 do tick(4)end
beacons_module.position=function()return nil end
BR.beacons=function()return {}end
require('hd2runtime/runtime/custom_mp_items').reset()
V.peers[P2].calls={{id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}}
I.calls_step(world)
for _=1,(mp_calls.WAIT/custom.STEP)+4 do tick(4);I.calls_step(world)end
assert(#SPAWNS==0,table.concat(logged,' | '))
assert(count('REFUSED: no carrier beacon or thrown ball with that network id was observed here in the last 45 s')==1,
    table.concat(logged,' | '))
""")

    def test_the_host_logs_every_step_of_a_request_it_accepts(self):
        self.lua(r"""
local world,M=machine(P1,true)
remote_call(8201,4160,P2,83,1)
V.peers[P2].calls={{id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}}
I.calls_step(world);I.calls_step(world);I.calls_step(world)
assert(#SPAWNS==1,table.concat(logged,' | '))
local tag='PELICAN REQUEST '..P2..'#1: '
assert(count('PELICAN REQUEST RECEIVED: sender peer '..P2..', seq 1, slot 1, beacon network id 4160, carrier hash '
    ..M.mp.carrier_hash..', custom pelican_close_air_support')==1,table.concat(logged,' | '))
for _,check in ipairs({'SEQUENCE','PICK','CARRIER','EVIDENCE','BEACON'})do
    assert(count(tag..check..' CHECK pass (')==1,check..' | '..table.concat(logged,' | '))
end
assert(count('CHECK FAIL')==0 and count('ACCEPTED (')==1)
-- Still published by the client: never logged or run again.
local n=#logged
I.calls_step(world);I.calls_step(world)
assert(#logged==n and #SPAWNS==1)
""")

    def test_each_refusal_names_its_check_and_the_identity_comes_from_the_beacons_carrier(self):
        self.lua(r"""
local world,M=machine(P1,true)
remote_call(8201,4160,P2,83,1)
local function request(fields)
    local r={id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}
    for k,v in pairs(fields)do r[k]=v end
    return r
end
-- PICK: another slot; CARRIER: another hash.
V.peers[P2].calls={request({seq=1,slot=0})};I.calls_step(world)
V.peers[P2].calls={request({seq=2,carrier='00000000'})};I.calls_step(world)
assert(count('PELICAN REQUEST '..P2..'#1: PICK CHECK FAIL (that player\'s synced loadout slot 0')==1
    and count('PELICAN REQUEST '..P2..'#2: CARRIER CHECK FAIL (its carrier map hash 00000000')==1,table.concat(logged,' | '))
-- EVIDENCE: the beacon it names is a Gas EAT carrier's beacon here (M-105 Stalwart -> eat17_gas), whatever id the
-- request names: refused (the identity is the observed carrier's, never the request's string).
remote_call(8203,4180,P2,9,0)
V.peers[P2].calls={request({seq=3,beacon=4180})};I.calls_step(world)
assert(count('PELICAN REQUEST '..P2..'#3: EVIDENCE CHECK FAIL (its observed beacon\'s carrier maps to eat17_gas here (the '
    ..'frozen carrier map), not pelican_close_air_support)')==1,table.concat(logged,' | '))
-- SEQUENCE: an older sequence never seen before (a stale or replayed request) is refused once, never run.
V.peers[P2].calls={request({seq=2,beacon=4160})};I.calls_step(world)
V.peers[P2].calls={request({seq=1,beacon=4160,slot=1})};I.calls_step(world)
assert(count('#1: SEQUENCE CHECK FAIL')==0,'seq 1 was decided already: not logged again')
V.peers[P2].calls={request({seq=0,beacon=4160})};I.calls_step(world);I.calls_step(world)
assert(count('PELICAN REQUEST '..P2..'#0: SEQUENCE CHECK FAIL (seq 0 is not newer than seq 3 already handled for that '
    ..'player: a stale or replayed request)')==1,table.concat(logged,' | '))
assert(#SPAWNS==0)
-- The host read every request it was sent (logged once each, whatever happened to it).
""")

    def test_the_host_spawns_at_a_remote_beacon_copys_creation_position(self):
        # Research section 18: beacons.position is nil for another machine's beacon copy, so r4/r5's host call had no
        # position for a client's call ("its beacon copy has no position here"): the copy's creation position is used.
        self.lua(r"""
local world,M=machine(P1,true)
beacons_module.position=function()return nil end
require('hd2runtime/runtime/custom_barrages').beacon_position=function(w,e)
    if e==8201 then return {x=12,y=-7,z=3,owned=false,source='element'}end
end
remote_call(8201,4160,P2,83,1)
V.peers[P2].calls={{id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}}
I.calls_step(world)
assert(#SPAWNS==1 and SPAWNS[1].position.x==12 and SPAWNS[1].position.y==-7,table.concat(logged,' | '))
assert(count('could not run it')==0)
""")

    def test_a_request_that_does_not_check_out_is_refused_once(self):
        self.lua(r"""
local world,M=machine(P1,true)
remote_call(8201,4160,P2,83,1)
local function request(fields)
    local r={id='pelican_close_air_support',beacon=4160,seq=1,slot=1,carrier=M.mp.carrier_hash}
    for k,v in pairs(fields)do r[k]=v end
    return r
end
-- Another slot than the synced one; another carrier map; a beacon another player threw: refused, nothing spawned.
V.peers[P2].calls={request({seq=1,slot=0})}
I.calls_step(world)
V.peers[P2].calls={request({seq=2,carrier='00000000'})}
I.calls_step(world)
remote_call(8202,4161,'9999999999999999',83,1)
V.peers[P2].calls={request({seq=3,beacon=4161})}
I.calls_step(world)
assert(#SPAWNS==0,table.concat(logged,' | '))
assert(count('REFUSED: that player\'s synced loadout slot 0 (frozen at the mission start) is not '
    ..'pelican_close_air_support')==1 and count('REFUSED: its carrier map hash 00000000 is not the host\'s')==1
    and count('REFUSED: its observed caller is 9999999999999999 (ball), not the sender')==1,table.concat(logged,' | '))
-- An unseen beacon: waited for, then refused; an older sequence: ignored.
V.peers[P2].calls={request({seq=4,beacon=4199})}
I.calls_step(world)
assert(count('waiting for its beacon')==1)
for _=1,(mp_calls.WAIT/custom.STEP)+4 do tick(4);I.calls_step(world)end
assert(count('REFUSED: no carrier beacon or thrown ball with that network id was observed here in the last 45 s')==1)
V.peers[P2].calls={request({seq=2})}
I.calls_step(world)
assert(#SPAWNS==0 and count('call seq 2')==1)
-- On a client nothing is ever run for another player.
""")


if __name__ == '__main__':
    unittest.main()
