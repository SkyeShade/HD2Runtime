"""proof/PelicanCasProof 0.1.1 (docs/research/pelican-cas-F5FEE03DCFDB.md): Pelican Close Air Support, the first custom
stratagem whose delivery is a Runtime-summoned game Pelican. Offline, the proof's own addon end to end on the event
world of the Gas Barrage proofs (the custom panel, the saved loadout, the mission record and HUD), with two owned
orbitals that are not payload-compatible with the 120mm: the Orbital EMS Strike (a BLUE beam, as in the game: never the
offensive carrier, 0.1.0's live carrier) and the Orbital Gatling Barrage (a red beam), the beacon manager of
tests/test_beacon_redirect.py and the Pelican world of tests/test_pelicans.py (the game's spawn request simulated):
  ship: the selection, the allocation (the Gas Barrage reserves its three payload-compatible carriers; the Pelican CAS
  takes the red Gatling Barrage, the EMS Strike refused as a support beacon), the code check, the carrier native;
  mission: the look and code applied, the beacon watch and the 60 s cooldown armed, the conversion, READY TO CALL; a
  carrier beacon neutralized in its first update, its landing recorded, the activation, one empty Pelican anchored at
  the landing position (the approach from the player's side), its hover over the beacon, the hold, the departure, the
  summary; the cooldown 60 s from the arrival; the carrier's own row cooldown never written;
  return to the ship: the carrier's look and code restored exactly."""
import json
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD, PROOF
from test_stratagem_slot_conversion import SLOT
from test_gas_barrage_mission_proof import HARNESS
from test_gas_barrage_payload_proof import FLOW3, PAYLOAD_FLOW

FOLDER = ROOT / 'proof/PelicanCasProof'
BODY = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')

CAS_HARNESS = HARNESS.replace("images.name(RESOURCE,'orbital_gas_barrage_masks')",
                              "images.name(RESOURCE,'pelican_close_air_support')")
assert CAS_HARNESS != HARNESS

# The Orbital EMS Strike (a fixture type 112) and the Orbital Gatling Barrage (109) at their catalogue roots: owned,
# selectable, enabled, unlimited, their reviewed presentation and native codes, not payload-compatible with the 120mm.
# Their beams are the game's (the fixture rows carry the observed +0xD4/+0xB8): the EMS blue, the Gatling red.
CAS_CARRIERS = FLOW3.replace('''local BIG380_ID,WALK_ID=3108516875,3279813377
''', '''local BIG380_ID,WALK_ID,EMS_ID,GATLING_ID=3108516875,3279813377,1280711447,2084654169
''').replace('''    {type=125,id=BIG380_ID,''', '''    {type=112,id=EMS_ID,package='0x1E6C958B95568DD7',
        payload=require('hd2runtime/domains/stratagem_authoring').stratagems['Orbital EMS Strike'].root.payloads[1],
        sequence={2,2,4,3},group=5,row=10,cooldown=180,fields=pres(EMS_ID)},
    {type=109,id=GATLING_ID,package='0x7D72A031B0B3C618',
        payload=require('hd2runtime/domains/stratagem_authoring').stratagems['Orbital Gatling Barrage'].root.payloads[1],
        sequence={2,3,4,1,1},group=5,row=3,cooldown=70,fields=pres(GATLING_ID)},
    {type=125,id=BIG380_ID,''').replace('''for _,kind in ipairs({118,136,106,125,127})do''',
    '''for _,kind in ipairs({118,136,106,125,127,112,109})do''').replace('''[BIG380_ID]=2,[WALK_ID]=2})''',
    '''[BIG380_ID]=2,[WALK_ID]=2,[EMS_ID]=2,[GATLING_ID]=2})''')
assert CAS_CARRIERS.count('EMS_ID') == 4 and CAS_CARRIERS.count('GATLING_ID') == 4

# The beacon manager and the Pelican world in one table (CT), so the harnesses together stay under Lua's 200 locals.
CAS_WORLD = r"""
local CT={calls={},next=9500}
;(function()   -- its own function: the main chunk's 200 locals are taken
    local BR=require('hd2runtime/runtime/beacon_redirect')
    local BD=require('hd2runtime/domains/beacon_redirect')
    BR.reset_for_tests();require('hd2runtime/runtime/beacons').reset_for_tests()
    require('hd2runtime/runtime/slot_cooldown').reset_for_tests()
    for _,pin in ipairs(BD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
    local CW=b.pointer(W.read(W.GAME+BD.path.world,8),0)
    local MGR=CW+BD.path.systems+BD.path.beacons
    local HANDLES,STATE,ELEMENTS=W.alloc(0x1000),W.alloc(0x3000),W.alloc(0x1000)
    W.write(MGR+0x50,W.u32(128))
    W.write(MGR+0x60,W.u64(HANDLES));W.write(MGR+0x68,W.u64(STATE));W.write(MGR+0x78,W.u64(ELEMENTS))
    local function f32(v)return b.encode(v,'f32')end
    -- A landed carrier beacon owned here (its state, mode 1) at (x, y, z), its countdown running.
    function CT.beacon(i,entity,kind,countdown,threshold,x,y,z)
        local handle=W.alloc(0x20);W.write(handle+8,W.u32(entity));W.write(HANDLES+i*8,W.u64(handle))
        W.write(ELEMENTS+i*0x40,f32(countdown)..f32(threshold)..W.u32(0x11)..W.u32(kind)..f32(x)..f32(y)..f32(z)
            ..f32(x)..f32(y)..f32(z)..W.u32(0)..string.rep('\0',0x10)..string.char(1)..'\0\0\0')
        W.write(STATE+i*0x8E8+BD.state.position,f32(x)..f32(y)..f32(z))
        W.write(STATE+i*0x8E8+0x8E0,W.u32(1)..string.char(0))
        W.write(MGR+0x34,W.u32(i+1)..W.u32(i+1))
    end
    function CT.activate(i)W.write(STATE+i*0x8E8+0x8E4,string.char(1))end
    function CT.type_at(i)return b.u32(W.read(ELEMENTS+i*0x40+0xC,4),0)end
    function CT.no_beacons()W.write(MGR+0x34,W.u32(0)..W.u32(0))end
    -- The Pelican world (tests/test_pelicans.py): the pins, the Transport, Behavior, transform, drop-position and
    -- flight components, the entity settings table with the Pelican registered, the spawn request simulated.
    local PE=require('hd2runtime/domains/pelican')
    require('hd2runtime/runtime/pelicans').reset_for_tests()
    require('hd2runtime/api/pelican').reset_for_tests()
    for _,pin in ipairs(PE.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
    local TC,BC,XC,F,AN,FT,SP=PE.components.transport,PE.components.behavior,PE.components.bearer,PE.flight,PE.anchor,
        PE.flightTarget,PE.spawn
    local P=BC.context
    local EMPTY=4294967295
    local function map(component,layout)
        local keys=W.alloc(64*8)
        for k=0,63 do W.write(keys+k*8,W.u32(EMPTY)..W.u32(0))end
        W.write(component+layout.keys,W.u64(keys))
        W.write(component+layout.capacity,W.u32(64));W.write(component+layout.empty,W.u32(EMPTY))
        W.write(component+layout.multiplier,W.u32(1))
        return function(entity,index)
            local slot=entity%64
            while b.u32(W.read(keys+slot*8,4),0)~=EMPTY and b.u32(W.read(keys+slot*8,4),0)~=entity do slot=(slot+1)%64 end
            W.write(keys+slot*8,W.u32(entity)..W.u32(index))
        end
    end
    local TCOMP,BCOMP,XCOMP,ACOMP,FCOMP=W.alloc(0x100),W.alloc(0x100),W.alloc(0x100),W.alloc(0x100),W.alloc(0x100)
    W.write(W.GAME+TC.global,W.u64(TCOMP));W.write(W.GAME+BC.global,W.u64(BCOMP));W.write(W.GAME+XC.global,W.u64(XCOMP))
    W.write(W.GAME+AN.global,W.u64(ACOMP));W.write(W.GAME+FT.global,W.u64(FCOMP))
    local THANDLES,TELEMENTS,BHANDLES,BRECORDS=W.alloc(0x1000),W.alloc(0x1000),W.alloc(0x1000),W.alloc(0x2000)
    W.write(TCOMP+TC.handles,W.u64(THANDLES));W.write(TCOMP+TC.elements,W.u64(TELEMENTS))
    W.write(BCOMP+BC.handles,W.u64(BHANDLES));W.write(BCOMP+BC.records,W.u64(BRECORDS))
    local XRECORDS,ARECORDS,FRECORDS=W.alloc(0x2000),W.alloc(0x1000),W.alloc(0x2000)
    W.write(XCOMP+XC.records,W.u64(XRECORDS));W.write(ACOMP+AN.records,W.u64(ARECORDS))
    W.write(FCOMP+FT.records,W.u64(FRECORDS))
    local bkey,xkey,fkey=map(BCOMP,BC),map(XCOMP,XC),map(FCOMP,FT)
    local akey=map(ACOMP,{keys=AN.mapKeys,capacity=AN.mapCapacity,empty=AN.mapEmpty,multiplier=AN.mapMultiplier})
    local PELICAN=b.unhex(PE.entity):reverse()
    function CT.tcount(n)W.write(TCOMP+TC.count,W.u32(n))end
    local function record(i)return BRECORDS+i*BC.stride end
    function CT.stage(i,s,flags)
        W.write(record(i)+P+F.stage,W.u32(s))
        if flags~=nil then W.write(record(i)+P+F.flags,W.u32(flags))end
    end
    function CT.stamp(i,member,us)W.write(record(i)+P+F[member],W.u64(us))end
    function CT.target(i,x,y,z)
        W.write(record(i)+P+F.target,f32(x)..f32(y)..f32(z))
        W.write(FRECORDS+i*FT.stride+FT.target,f32(x)..f32(y)..f32(z))
    end
    function CT.position(i,x,y,z)W.write(XRECORDS+i*XC.stride+XC.position,f32(x)..f32(y)..f32(z))end
    local cworld=b.pointer(W.read(W.GAME+SP.world,8),0)
    W.write(W.GAME+SP.rva,b.unhex(SP.prologue))
    local tab=W.alloc(0x1000)
    W.write(cworld+SP.settingsTable,W.u64(tab))
    local lo,hi=b.u32(PELICAN,0),b.u32(PELICAN,4)
    local slot=((hi%SP.settingsSlots)*(4294967296%SP.settingsSlots)+lo%SP.settingsSlots)%SP.settingsSlots
    W.write(tab+slot*16,PELICAN..W.u32(3)..W.u32(0))
    W.write(tab+SP.settingsBase+3*SP.settingsStride,f32(0)..f32(2))
    W.runtime.native_spawn_pelican=function(entry,x,y,z,fx,fy,ax,ay,az)
        CT.calls[#CT.calls+1]={x=x,y=y,z=z,fx=fx,fy=fy,ax=ax,ay=ay,az=az}
        local i=b.u32(W.read(TCOMP+TC.count,4),0)
        CT.next=CT.next+1
        local entity=CT.next
        local handle=W.alloc(0x20)
        W.write(handle,PELICAN..W.u32(entity)..W.u32(0)..W.u32(700+i))
        W.write(THANDLES+i*8,W.u64(handle))
        W.write(TELEMENTS+i*TC.stride,string.rep('\0',TC.stride))
        bkey(entity,i);xkey(entity,i);akey(entity,i);fkey(entity,i)
        W.write(BHANDLES+i*8,W.u64(W.alloc(0x18)))
        W.write(record(i),W.u32(667)..string.rep('\0',BC.stride-4))
        W.write(ARECORDS+i*AN.stride+AN.position,f32(ax)..f32(ay)..f32(az))
        CT.stage(i,1,0);CT.position(i,x,y,z);CT.tcount(i+1)
        return entity
    end
    -- The local player (avatar 100, unit 7100) resolvable through the network-id map in the component world.
    function CT.player(x,y,z)
        local A=require('hd2runtime/domains/event_natives').playerAvatars
        local slots_=W.alloc(64*8)
        for k=0,63 do W.write(slots_+k*8,W.u32(0x7FFF)..W.u32(0))end
        W.write(slots_+(100%64)*8,W.u32(100)..W.u32(0))
        W.write(cworld+A.mapSlots,W.u64(slots_));W.write(cworld+A.mapCapacity,W.u32(64))
        W.write(cworld+A.mapEmpty,W.u32(0x7FFF));W.write(cworld+A.mapMultiplier,W.u32(1))
        W.write(cworld+A.entityBase,W.u32(100))
        W.unit(7100,x,y,z)
    end
    -- The game's call of the converted entry 2: its activation, its arrival `inbound` s later and the carrier's own end.
    function CT.call(h,at,inbound,own)
        local e=h.record+0x38+0x188+2*0x30
        local arrival=at+math.floor(inbound*1000000)
        local function put(o,n)W.write(e+o,W.u32(n%4294967296)..W.u32(math.floor(n/4294967296)))end
        put(0x10,at);put(0x20,arrival);put(0x18,arrival+math.floor(own*1000000))
        return arrival
    end
    function CT.entry_end(h)
        local s=W.read(h.record+0x38+0x188+2*0x30+0x18,8)
        return b.u32(s,0)+b.u32(s,4)*4294967296
    end
end)()
function CT.lines(text)local out={};for _,line in ipairs(logged)do if line:find(text,1,true)then out[#out+1]=line end end
    return table.concat(out,' | ')end
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], BODY)


class PelicanCasProofTests(unittest.TestCase):
    def lua(self, body):
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_pelican_cas_proof')
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(wrapped) + '\nlocal RESOURCE='
            + lua_literal(resource) + PROOF + CAS_HARNESS + CAS_CARRIERS + PAYLOAD_FLOW + CAS_WORLD
            # The body in its own function: the harnesses fill the main chunk's 200 locals.
            + 'return (function()\nlocal lines=CT.lines\n' + body + '\nend)()\n'), b'ok')

    def test_the_proof_sources(self):
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.1')
        self.assertIn("local BUILD='0.1.1 RED-BEACON CARRIER BUILD'", BODY)
        self.assertNotIn("PELICAN CAS CALL-IN BUILD'", BODY)
        code = '\n'.join(line.split('--')[0] for line in BODY.splitlines())
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write(', 'native_spawn_pelican',
                'pelicans.hold', 'pelicans.spawn', 'pelicans.request', 'transaction', 'bombardment_payload',
                'convert_with_payload', 'apply_payload', 'beacon_reader.apply', 'redirect.apply'):
            self.assertNotIn(forbidden, code)
        # The Pelican only through the public API; the beacon only through its guarded first-update watch.
        self.assertEqual(code.count('hd2.pelican.spawn('), 1)
        self.assertEqual(code.count('beacons.watch('), 1)
        self.assertIn("local CODE={'left','down','left','up','left','up'}", code)
        self.assertIn("local function decide()return {delivery='none'}end", code)
        self.assertIn('local HOVER,COOLDOWN=60,60', code)
        self.assertEqual(sorted(p.name for p in (FOLDER / 'images').iterdir()), ['pelican_close_air_support.png'])
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import hd2_image
        hd2_image.icon_texture((FOLDER / 'images/pelican_close_air_support.png').read_bytes())

    def test_the_call_summons_an_empty_pelican_over_the_beacon_and_the_carrier_is_restored(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
local EMS,GATLING=112,109
local NATIVE_EMS,NATIVE_GATLING=W.read(ROW[EMS],400),W.read(ROW[GATLING],400)
local token_row=W.read(ROW118,400)
to_mission()
assert(count('PelicanCasProof 0.1.1 RED-BEACON CARRIER BUILD')==1)
-- SHIP: the allocation. The Gas Barrage reserves its payload-compatible carriers; the EMS Strike is an orbital with a
-- BLUE beacon: refused as a carrier of an offensive custom stratagem; the Pelican CAS takes the red Gatling Barrage.
assert(count('CARRIER CANDIDATE: Orbital EMS Strike (type 112, stable id 1280711447): family = orbital '
    ..'(BombardmentComponentData, class 1), beacon_category = support (blue beam, row +0xD4 = 2; red ping, +0xB8 = 0): '
    ..'owned=true selectable=true enabled=true unlimited=true in_loadout=false special_case=false package_available=true '
    ..'presentation=true code=true -> not offensive: a support beacon (blue beam, red ping)')==1,lines('CARRIER'))
assert(count('CARRIER CANDIDATE: Orbital Gatling Barrage (type 109, stable id 2084654169): family = orbital '
    ..'(BombardmentComponentData, class 1), beacon_category = offensive (red beam, row +0xD4 = 1; red ping, +0xB8 = 0)')==1
    and count('-> SELECTED')==1,lines('CARRIER CANDIDATE'))
assert(count('CARRIER CANDIDATE: Orbital Napalm Barrage (type 106, stable id 2902516083')==1
    and count('-> red, but taken by Gas Barrage')==1 and count('-> red, but RESERVED by Gas Barrage (never shared)')==2,
    lines('CARRIER CANDIDATE'))
assert(count('CUSTOM CARRIER: Gas Barrage = Orbital 380mm HE Barrage (orbital, red beacon), Pelican CAS = Orbital '
    ..'Gatling Barrage (orbital, red beacon); distinct = true')==1,lines('CUSTOM CARRIER'))
assert(count('CARRIER: Orbital Gatling Barrage SELECTED for the Pelican CAS (type 109, stable id 2084654169): family = '
    ..'orbital (class 1), beacon_category = offensive (a red beacon, red ping), tier 1 (4 red eligible, 3 taken or '
    ..'reserved by an earlier custom stratagem)')==1,lines('CARRIER:'))
assert(count('CODE CHECK: the Pelican CAS code left down left up left up for the carrier Orbital Gatling Barrage (stable '
    ..'id 2084654169): its native code read from its row first: right down left up up')==1
    and count('SAFE: applied at mission start')==1,lines('CODE CHECK'))
assert(count('READY: start a SOLO mission')>=1,lines('PRE-MISSION'))
assert(W.read(ROW[EMS],400)==NATIVE_EMS and W.read(ROW[GATLING],400)==NATIVE_GATLING and W.read(ROW118,400)==token_row,
    'nothing written aboard the ship')
-- MISSION: the look and code applied, the watch and the cooldown armed, the conversion, READY TO CALL.
local h=start_mission()
CT.player(0,0,0)
tick(64)
assert(count('] MISSION START: carrier presentation APPLIED (before')==1 and count('MISSION START: the beacon watch is armed (every '
    ..'beacon of Orbital Gatling Barrage neutralized in its first update) and the 60 s cooldown armed; converting the '
    ..'virtual slot')==1,lines('MISSION START'))
assert(count('MISSION START: conversion APPLIED: loadout slot 0 = record entry 2 -> the carrier Orbital Gatling Barrage')==1,
    lines('MISSION START'))
assert(count('READY TO CALL: the virtual Pelican CAS slot is the carrier Orbital Gatling Barrage, presenting as Pelican Close '
    ..'Air Support with the Pelican CAS code (left down left up left up)')==1,lines('READY'))
assert(count('COOLDOWN: armed for the Pelican CAS slot (carrier Orbital Gatling Barrage, its own row cooldown 70.0 s, never '
    ..'written)')==1,lines('COOLDOWN'))
-- THE CALL: the carrier's beacon lands at (40, 30, 2), 50 m from you; its delivery neutralized in its first update.
local C0=165760761
BOMB.set_clock(C0)
CT.beacon(0,7001,GATLING,8,3,40,30,2)
local arrival=CT.call(h,C0-300000,5,59.85)
tick()
assert(CT.type_at(0)==0,'the beacon was not neutralized')
assert(count('BEACON CREATED (call 1): the carrier Orbital Gatling Barrage\'s beacon 7001 (type 109')==1,lines('BEACON'))
assert(count('BEACON LANDED (call 1): beacon 7001 at (40.0, 30.0, 2.0)')==1,lines('BEACON'))
assert(count('BEACON NEUTRALIZED (call 1): beacon 7001 in its first update: delivery Orbital Gatling Barrage -> none (1 '
    ..'write, verified true): the carrier\'s own payload will not execute')==1,lines('BEACON'))
tick(2)
assert(count('COOLDOWN: Pelican CAS override = 60.0 s from the arrival (record entry 2, loadout slot 0')==1
    and CT.entry_end(h)==arrival+60000000,lines('COOLDOWN'))
-- The activation: one empty Pelican anchored at the landing position, approaching from your side.
BOMB.set_clock(arrival)
CT.activate(0)
tick()
assert(count('BEACON ACTIVATED (call 1): beacon 7001')==1 and count('the delivery the game had: none (type 0); at (40.0, '
    ..'30.0, 2.0), 0.0 m from its landing position')==1,lines('BEACON ACTIVATED'))
assert(count('PELICAN CAS REQUESTED (call 1): one empty Pelican anchored at the beacon landing position (40.0, 30.0, 2.0) '
    ..'(hover 60 s after its release; created 250.0 m back along your heading and 80.0 m up): status requested')==1,
    lines('PELICAN CAS'))
tick()
local c=CT.calls[1]
assert(#CT.calls==1 and c.ax==40 and c.ay==30 and c.az==2,'anchored at the landing position')
assert(math.abs(c.fx-0.8)<1e-6 and math.abs(c.fy-0.6)<1e-6 and math.abs(c.x+160)<1e-3 and math.abs(c.y+120)<1e-3
    and c.z==82,'created behind you: '..c.x..', '..c.y..', '..c.z)
assert(count('PELICAN CAS SPAWNED (call 1): entity 9501 (network id 700): empty')==1
    and count('its anchor (40.0, 30.0, 2.0) read back, 0.0 m from the beacon landing position (40.0, 30.0, 2.0)')==1,
    lines('PELICAN CAS'))
-- The flight: to the hover point over the beacon, then the hover.
BOMB.set_clock(arrival+8000000);CT.stage(0,3,0);CT.target(0,40,31,17);tick()
BOMB.set_clock(arrival+15000000);CT.stage(0,6,0);CT.stamp(0,'hoverStart',arrival+15000000);CT.position(0,40,31,17)
tick()
assert(count('PELICAN CAS HOVERING (call 1): entity 9501 at 15.0 s; hover point (40.0, 31.0, 17.0): 1.0 m from the '
    ..'beacon horizontally, 15.0 m above it -> AT THE BEACON')==1,lines('PELICAN CAS'))
assert(count('PELICAN CAS MOVERS (INTERNAL, read-only; call 1): entity 9501: the flight component holds it (record 0) '
    ..'(its target (40.0, 31.0, 17.0), 1.0 m from the beacon horizontally); the ground mover not; the other mover not -> '
    ..'the flight component alone holds it')==1,lines('MOVERS'))
BOMB.set_clock(arrival+20000000);CT.stage(0,6,1);CT.stamp(0,'releaseTime',arrival+20000000);tick()
assert(count('PELICAN CAS HELD (call 1): entity 9501: departs 60.0 s after its release (native 0.6 s); verified true')==1,
    lines('PELICAN CAS'))
-- You walk away; it stays over the beacon.
CT.player(-60,-50,0)
tick(80)
assert(count('PELICAN CAS STATE (call 1): entity 9501 stage 6 released true cargo false at (40.0, 31.0, 17.0): 1.0 m from '
    ..'the beacon horizontally, 15.0 m above it')>=2,lines('PELICAN CAS STATE'))
BOMB.set_clock(arrival+80000000);CT.stage(0,8,1);tick()
assert(count('PELICAN CAS DEPARTING (call 1): entity 9501: stage 8, 60.0 s after its release')==1,lines('DEPARTING'))
BOMB.set_clock(arrival+94000000);CT.tcount(0);tick()
assert(count('PELICAN CAS GONE (call 1): entity 9501')==1,lines('GONE'))
assert(count('PELICAN CAS SUMMARY (call 1): entity 9501: spawned empty at the beacon\'s activation; hovered 60.0 s after '
    ..'its release (asked 60)')==1 and count('-> PASS: it held over the beacon, not over you')==1,lines('SUMMARY'))
CT.no_beacons();tick(2)
assert(count('BEACON GONE (call 1): beacon 7001')==1,lines('BEACON GONE'))
-- The carrier's own row cooldown and its payload were never written; the token row is native.
local now=W.read(ROW[GATLING],400)
assert(now:sub(0x69,0x70)==NATIVE_GATLING:sub(0x69,0x70)and W.read(ROW118,400)==token_row
    and W.read(ROW[EMS],400)==NATIVE_EMS)
assert(count('REFUSED')==0 and count('callback failed')==0 and count('TEST REFUSED')==0,table.concat(logged,' | '))
-- RETURN TO SHIP: the look and code restored exactly.
end_mission(h)
tick(40)
assert(count('] RETURN TO SHIP: carrier presentation RESTORED')==1,lines('RETURN TO SHIP'))
assert(W.read(ROW[GATLING],400)==NATIVE_GATLING,'the carrier row is not native again')
done()
return 'ok'
''')

    def test_with_the_gatling_in_the_loadout_no_red_carrier_is_left_and_the_mission_is_refused(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(41);native_append(22);native_append(109)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=3193297673},{id=ID22},{id=GATLING_ID}})
tick(80)
-- Only the blue EMS Strike is left unreserved: it is never taken (the fallback is refuse).
assert(count('CUSTOM CARRIER: Gas Barrage = Orbital 380mm HE Barrage (orbital, red beacon), Pelican CAS = REFUSED (no '
    ..'unused red (offensive) carrier: 3 red eligible, 3 taken or reserved by an earlier custom stratagem')==1
    and count('fallback: refuse)')==1,lines('CUSTOM CARRIER'))
assert(count('CARRIER: none for the Pelican CAS')==1 and count('NOT READY: no unused red-beacon (offensive) carrier')>=1,
    lines('CARRIER'))
mission({host=true})
local record,hud=mission_record({118,41,22,109})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
CT.player(0,0,0)
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): no unused red-beacon (offensive) '
    ..'carrier for the current loadout')==1,lines('MISSION START'))
assert(count('] MISSION START: carrier presentation APPLIED')==0 and #CT.calls==0)
done()
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
