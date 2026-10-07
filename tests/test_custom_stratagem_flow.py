"""The custom stratagem API end to end (runtime/custom_stratagems.lua; docs/custom-stratagem-api.md), with the example
mods themselves (proof/PelicanCasExample, proof/GasBarrageExample, proof/GasEatExample) on the offline world of the
Pelican CAS proof (tests/test_pelican_cas_proof.py: the custom panel, the saved loadout, the mission record and HUD, the
beacon manager, the Pelican world):
  ship: three custom stratagems in ONE panel; two of them selected into two slots of one loadout beside vanilla
  stratagems; their carriers allocated by policy (two distinct red orbitals), native aboard the ship;
  mission: each in turn: assets, its carrier's look and code, its cooldown, only its own slot converted; both READY;
  a beacon of each carrier changed in its first update (and only those); the calls' contexts; the Pelican requested at
  the landing position with its gun, orbit and credit; the gas barrage started at the landing position; each slot's
  own 60 s cooldown; return to the ship: both carriers restored exactly; the token and every other row untouched."""
import json
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD, PROOF
from test_stratagem_slot_conversion import SLOT
from test_gas_barrage_mission_proof import HARNESS
from test_gas_barrage_payload_proof import PAYLOAD_FLOW
from test_pelican_cas_proof import CAS_CARRIERS, CAS_WORLD

# A support weapon the account owns (the MG-43 Machine Gun: a blue beacon; its call-in package is its weapon's, +0xF8)
# and the EAT-17 itself (type 147; the delivery), at their catalogue roots (support weapons: +0xA8 = 0).
EAT_CARRIERS = CAS_CARRIERS.replace('''    {type=112,id=EMS_ID,''', '''    {type=60,id=458198946,package='0x0000000000000000',
        payloads={'0x94C5114EBA59AA21','0x73F8498BFFDCF415'},sequence={3,4,3,1,2},group=7,row=17,cooldown=480,
        fields=pres(458198946)},
    {type=147,id=3413606544,package='0x0000000000000000',payloads={'0x0DC7A18342B62BEC','0x73F8498BFFDCF415'},
        sequence={3,3,4,1,2},group=7,row=10,cooldown=70},
    {type=112,id=EMS_ID,''').replace('''for _,kind in ipairs({118,136,106,125,127,112,109})do''',
    '''for _,kind in ipairs({118,136,106,125,127,112,109,60})do''').replace(
    '''[EMS_ID]=2,[GATLING_ID]=2})''', '''[EMS_ID]=2,[GATLING_ID]=2,[458198946]=2})''')
assert EAT_CARRIERS.count('458198946') == 3

EXAMPLES = {name: ROOT / 'proof' / name for name in ('PelicanCasExample', 'GasBarrageExample', 'GasEatExample')}
BANNERS = {'PelicanCasExample': '0.1.8 HOST PELICAN BUILD', 'GasBarrageExample': '0.1.7 NATIVE BARRAGE BUILD',
    'GasEatExample': '0.1.7 MULTIPLAYER PROVENANCE BUILD'}
ICONS = {'PelicanCasExample': 'pelican_close_air_support', 'GasBarrageExample': 'orbital_gas_barrage',
    'GasEatExample': 'eat17_gas'}


# The sources these flows were written against: GasBarrageExample 0.1.7 (frozen when the example became a
# custom_stratagems.json project, 2026-10-06; same resource id), the others as they are.
FROZEN = {'GasBarrageExample': ROOT / 'tests/fixtures/example_addons/GasBarrageExample-0.1.7.lua'}


def source(name):
    return (FROZEN.get(name) or EXAMPLES[name] / 'src/addon.lua').read_text(encoding='utf-8')


def addon(name):
    from test_event_scripting import SDK
    folder = EXAMPLES[name]
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = source(name)
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


# Every example's icon resident (their own textures and materials) beside the font.
FLOW_HARNESS = HARNESS.replace(
    "local ICON_NAME=images.name(RESOURCE,'orbital_gas_barrage_masks')",
    "local ICON_NAME=images.name(RESOURCE,'pelican_close_air_support')\n"
    "local GAS_ICON=images.name(GAS_RESOURCE,'orbital_gas_barrage')\n"
    "local EAT_ICON=images.name(EAT_RESOURCE,'eat17_gas')").replace(
    "W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT}})",
    "W.icon_resources({textures={ICON_NAME,GAS_ICON,EAT_ICON},materials={ICON_NAME,GAS_ICON,EAT_ICON,FONT},"
    "fonts={FONT}})")
assert FLOW_HARNESS.count('GAS_ICON') == 3


COMMON = r"""
rawset(_G,'ModOptionsMenu',MENU)
local NAPALM,GATLING=106,109
local native={}
for _,kind in ipairs({NAPALM,GATLING,112,118,136,41})do native[kind]=W.read(ROW[kind],400)end
examples()
tick(40)
ship({})
tick(4)
"""


class CustomStratagemFlowTests(unittest.TestCase):
    def lua(self, body, carriers=CAS_CARRIERS):
        pelican, pelican_addon = addon('PelicanCasExample')
        gas, gas_addon = addon('GasBarrageExample')
        eat, eat_addon = addon('GasEatExample')
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(pelican_addon) + '\nlocal RESOURCE='
            + lua_literal(pelican) + '\nlocal GAS_ADDON=' + lua_literal(gas_addon) + '\nlocal GAS_RESOURCE='
            + lua_literal(gas) + '\nlocal EAT_ADDON=' + lua_literal(eat_addon) + '\nlocal EAT_RESOURCE='
            + lua_literal(eat) + PROOF + FLOW_HARNESS + carriers + PAYLOAD_FLOW + CAS_WORLD
            + 'return (function()\nlocal lines=CT.lines\n'
            + "local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()\n"
            # The token path end to end (the Runtime's own fallback; the carrier itself is the default since r44:
            # tests/test_carrier_in_slot.py).
            + "custom.set_default_selection_for_tests('token')\n"
            + "require('hd2runtime/runtime/spawned_instances').reset_for_tests()\n"
            + "require('hd2runtime/runtime/pelican_gunship').reset_for_tests()\n"
            + "local function examples()proof();assert(loadstring(GAS_ADDON,'@'..GAS_RESOURCE))();"
            + "assert(loadstring(EAT_ADDON,'@'..EAT_RESOURCE))()end\n"
            + body + '\nend)()\n'), b'ok')

    def test_the_example_sources_use_the_public_api_only(self):
        for name, folder in EXAMPLES.items():
            body = source(name)
            code = '\n'.join(line.split('--')[0] for line in body.splitlines())
            if name not in FROZEN:
                self.assertEqual((folder / 'VERSION').read_text(encoding='utf-8').strip(), BANNERS[name].split()[0])
            self.assertIn("local BUILD='%s'" % BANNERS[name], code)
            for old in ('0.1.0 CUSTOM STRATAGEM API BUILD', '0.1.1 PACKAGED ICON BUILD', '0.1.1 BLUE SUPPORT BUILD',
                    '0.1.2 EDITABLE PNG BUILD', '0.1.3 EDITED ICONS BUILD', '0.1.4 SELECTOR UX BUILD',
                    '0.1.5 PAYLOAD FAMILIES BUILD', '0.1.6 FROZEN GUN BUILD'):
                self.assertNotIn(old, code)
            # Its icon is its own packaged image, referenced directly.
            self.assertIn("icon=hd2.resources.image('%s')," % ICONS[name], code)
            self.assertEqual(sorted(p.name for p in (folder / 'images').iterdir()), [ICONS[name] + '.png'])
            for forbidden in ("require('hd2runtime", 'ffi', 'VirtualProtect', 'WriteProcessMemory', '.write(',
                    'transaction', 'native_'):
                self.assertNotIn(forbidden, code, name)
            self.assertEqual(code.count('hd2.custom_stratagem.register('), 1, name)
            import sys
            sys.path.insert(0, str(ROOT / 'scripts'))
            import hd2_image
            for image in (folder / 'images').iterdir():
                hd2_image.icon_texture(image.read_bytes())

    def test_two_custom_stratagems_in_one_loadout_from_the_ship_to_the_calls_and_back(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
local NAPALM,GATLING,EMS=106,109,112
local native={}
for _,kind in ipairs({NAPALM,GATLING,EMS,118,136,41})do native[kind]=W.read(ROW[kind],400)end
-- The executor itself is tested on its own (tests/test_bombardment_executor.py): here, what the call asks of it.
local barrages={}
require('hd2runtime/runtime/bombardment_executor').start=function(spec,callback)
    barrages[#barrages+1]=spec;return {status='active',cancel=function()end}
end
examples()
assert(count('PelicanCasExample 0.1.8 HOST PELICAN BUILD')==1
    and count('GasBarrageExample 0.1.7 NATIVE BARRAGE BUILD')==1
    and count('GasEatExample 0.1.7 MULTIPLAYER PROVENANCE BUILD')==1 and count('0.1.4 ')==0,
    table.concat(logged,' | '))
-- Their icons: each mod's own packaged image (its resource and id).
local V0=require('hd2runtime/runtime/virtual_stratagems')
for id,image in pairs({pelican_close_air_support=ICON_NAME,orbital_gas_barrage=GAS_ICON,eat17_gas=EAT_ICON})do
    local hi,lo=images.hash(image)
    assert(images.bytes(V0.get(id).display.icon)==W.u32(lo)..W.u32(hi),'the icon of '..id..' is not its own image')
end
-- The offensive ones keep the token's colours; the support Gas EAT takes a blue support stratagem's.
assert(V0.get('pelican_close_air_support').display.coloursId==nil and V0.get('orbital_gas_barrage').display.coloursId==nil)
assert(V0.get('eat17_gas').display.colours=='EAT-17 Expendable Anti-Tank'
    and V0.get('eat17_gas').display.coloursId==3413606544)
assert(count('REGISTERED eat17_gas (EAT-17G Gas Expendable Anti-Tank)')==1 and count('; ship icon colours: EAT-17 '
    ..'Expendable Anti-Tank\'s (support, blue)')==1 and count('ship icon colours')==1,lines('REGISTERED'))
assert(count('custom stratagem REGISTERED pelican_close_air_support (Pelican Close Air Support) by '
    ..'mods/skyeshade/hd2runtime_pelican_cas_example: code left down left up left up, cooldown 60 s, carrier policy: '
    ..'offensive beacon, prefer orbital; delivery a Pelican that holds over the beacon 60 s, orbiting it')==1,
    lines('REGISTERED'))
assert(count('REGISTERED orbital_gas_barrage (Orbital Gas Barrage)')==1 and count('delivery the Orbital 120mm HE Barrage\'s '
    ..'own native barrage (every player\'s machine fires it), each of its shells (194, 137) exploding as Orbital Gas '
    ..'Strike\'s')==1,lines('REGISTERED'))
assert(count('REGISTERED eat17_gas (EAT-17G Gas Expendable Anti-Tank)')==1 and count('delivery the vanilla EAT-17 '
    ..'Expendable Anti-Tank')==1,lines('REGISTERED'))
-- SHIP: one panel for the three; Pelican CAS into slot 0 (F7 focuses, F7 selects), Gas Barrage into slot 1.
tick(40)
ship({})
tick(4)
select_into(0)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',1);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F7')
tick(30)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
local V=require('hd2runtime/runtime/stratagem_selector').virtual_slots()
assert(V and V.slots[0].definition=='pelican_close_air_support'and V.slots[1].definition=='orbital_gas_barrage',
    require('hd2runtime/runtime/stratagem_selector').slots_text(V)..' | '..lines('SHIP'))
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=ID22},{id=1298599997}})
tick(80)
-- Two red orbitals, distinct; the 120mm and the Gas Strike (Gas Barrage assets) never carriers.
assert(count('CUSTOM CARRIERS: Orbital Gas Barrage = Orbital Gatling Barrage (orbital, red beacon), Pelican Close Air '
    ..'Support = Orbital Napalm Barrage (orbital, red beacon); distinct = true (aboard the ship')==1,lines('CUSTOM CARRIERS'))
assert(count('PRE-MISSION (pelican_close_air_support): READY: carrier Orbital Napalm Barrage')==1
    and count('PRE-MISSION (orbital_gas_barrage): READY: carrier Orbital Gatling Barrage')==1,lines('PRE-MISSION'))
for kind,bytes in pairs(native)do assert(W.read(ROW[kind],400)==bytes,'written aboard the ship: '..kind)end
-- MISSION: slots 0 and 1 hold the token (record entries 2 and 3).
mission({host=true})
local record,hud=mission_record({118,118,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
CT.player(0,0,0)
tick(120)
assert(count('MISSION (orbital_gas_barrage): READY TO CALL: loadout slot 1 = Orbital Gatling Barrage, presenting as '
    ..'Orbital Gas Barrage; code up up down down')==1,lines('MISSION'))
assert(count('MISSION (pelican_close_air_support): READY TO CALL: loadout slot 0 = Orbital Napalm Barrage, presenting '
    ..'as Pelican Close Air Support; code left down left up left up')==1,lines('MISSION'))
local function entry(i)return b.u32(W.read(h.record+0x38+0x188+i*0x30,4),0)end
assert(entry(2)==NAPALM and entry(3)==GATLING and entry(4)==22 and entry(5)==130,'converted: '..entry(2)..','..entry(3))
assert(W.read(ROW[118],400)==native[118]and W.read(ROW[136],400)==native[136]and W.read(ROW[41],400)==native[41],
    'the token and the donors are never written')
assert(W.read(ROW[EMS],400)==native[EMS],'an unused carrier is never written')
-- THE CALLS: a Gatling Barrage beacon (Gas Barrage: its delivery becomes the 120mm's own barrage, type 136) and a
-- Napalm beacon (Pelican CAS: neutralized), changed in their first update.
local C0=165760761
BOMB.set_clock(C0)
CT.beacon(0,7001,GATLING,8,3,40,30,2)
tick()
assert(CT.type_at(0)==136,'the Gas Barrage beacon was not redirected to the 120mm: '..CT.type_at(0))
assert(count('orbital_gas_barrage#1: BEACON 7001 (the carrier Orbital Gatling Barrage\'s own beam')==1
    and count('orbital_gas_barrage#1: beacon 7001 delivery Orbital Gatling Barrage -> Orbital 120mm HE Barrage in its '
    ..'first update (1 write, verified true)')==1,lines('#1'))
assert(count('orbital_gas_barrage#1: LANDED at (40.0, 30.0, 2.0)')==1,lines('LANDED'))
CT.beacon(1,7002,NAPALM,8,3,-20,10,1)
tick()
assert(CT.type_at(1)==0 and count('pelican_close_air_support#1: beacon 7002 delivery Orbital Napalm Barrage -> none')==1,
    lines('#1'))
-- Each call-in's cooldown: the Pelican CAS slot (entry 2) and the Gas Barrage slot (entry 3), each its own 60 s from
-- its own arrival; the carriers' own row cooldowns never written.
local function call_entry(index,at,inbound,own)
    local e=h.record+0x38+0x188+index*0x30
    local arrival=at+math.floor(inbound*1000000)
    local function put(o,n)W.write(e+o,W.u32(n%4294967296)..W.u32(math.floor(n/4294967296)))end
    put(0x10,at);put(0x20,arrival);put(0x18,arrival+math.floor(own*1000000))
    return arrival
end
local function entry_end(index)
    local s=W.read(h.record+0x38+0x188+index*0x30+0x18,8)
    return b.u32(s,0)+b.u32(s,4)*4294967296
end
local a2=call_entry(2,C0-300000,5,239.9)
local a3=call_entry(3,C0-200000,4,69.9)
tick(2)
assert(entry_end(2)==a2+60000000 and entry_end(3)==a3+60000000,'the cooldowns: '..entry_end(2)..', '..entry_end(3))
assert(count('pelican_close_air_support: COOLDOWN 60.0 s from the call-in\'s arrival (record entry 2')==1
    and count('orbital_gas_barrage: COOLDOWN 60.0 s from the call-in\'s arrival (record entry 3')==1,lines('COOLDOWN'))
-- The activations: the game's own 120mm barrage over the Gas Barrage beacon (no Runtime bombardment), one Pelican over
-- the other, each with its own context.
BOMB.set_clock(C0+5000000)
CT.activate(0);CT.activate(1)
tick(2)
assert(#barrages==0,'the native barrage is the game\'s: the Runtime bombardment is never started')
-- The game creates the 120mm's barrage at the activation; the call waits for it, taken at its first shell (its carrier
-- type, its creator, its target: tests/test_custom_mp_barrage.py).
assert(count('orbital_gas_barrage#1: BARRAGE: the native Orbital 120mm HE Barrage barrage of this call is recognised at '
    ..'its first shell')==1 and count('DELIVERED')==0,lines('orbital_gas_barrage#1'))
assert(#CT.calls==1 and CT.calls[1].ax==-20 and CT.calls[1].ay==10,'the Pelican over its own beacon')
tick(2)
assert(count('pelican_close_air_support#1: PELICAN: 9501 spawned on the host for this player; on its way to the '
    ..'beacon')==1,lines('PELICAN'))
-- The Pelican is associated with its call; the instance registry names it.
local inst=require('hd2runtime/api/custom_stratagem').instance_of(9501)
assert(inst and inst.call_id=='pelican_close_air_support#1'and inst.role=='pelican',tostring(inst and inst.call_id))
-- Its chin turret (associated as the gunship does) kills an enemy: the kill is reported against the call; a death by
-- anything else is not.
local I=require('hd2runtime/runtime/spawned_instances')
assert(I.associate_child(9501,8102,'weapon'))
local world=require('hd2runtime/runtime/event_world').open()
W.add{entity=5555,type='73F8498BFFDCF415',unit=7555,health=0}
W.add{entity=5556,type='73F8498BFFDCF415',unit=7556,health=0}
do
    local wm=require('hd2runtime/runtime/event_world')
    local st=wm.entity_state(world,5555)
    W.write(st.header.records+st.index*440+0x30,W.u32(8102)..W.u32(0)..W.u32(0x1234)..W.u32(0))
    local st2=wm.entity_state(world,5556)
    W.write(st2.header.records+st2.index*440+0x30,W.u32(100)..W.u32(0)..W.u32(0x1234)..W.u32(0))
end
require('hd2runtime/runtime/events').dispatch('entity_died',{entity_id=5555,semantic_id='enemy/v1/test/victim',
    killer_peer='0000000000001234',local_killer=true})
require('hd2runtime/runtime/events').dispatch('entity_died',{entity_id=5556,semantic_id='enemy/v1/test/other',
    killer_peer='0000000000001234',local_killer=true})
assert(count('pelican_close_air_support#1: KILL: victim 5555 (enemy/v1/test/victim) by its weapon 8102 -> credited to '
    ..'0000000000001234 (you)')==1 and count('KILL: victim 5556')==0,lines('KILL'))
-- Every other beacon is left alone (a vanilla beacon of another type: nothing written, no call).
CT.beacon(2,7003,22,8,3,5,5,0)
tick()
assert(CT.type_at(2)==22 and count('#2:')==0,'a vanilla beacon was changed')
assert(count('callback failed')==0 and count('failed:')==0,table.concat(logged,' | '))
-- RETURN TO THE SHIP: both carriers restored exactly; nothing else was ever written.
end_mission(h)
tick(40)
assert(count('RETURN TO SHIP: Orbital Gatling Barrage presentation RESTORED')==1
    and count('RETURN TO SHIP: Orbital Napalm Barrage presentation RESTORED')==1,lines('RESTORED'))
for kind,bytes in pairs(native)do assert(W.read(ROW[kind],400)==bytes,'not native again: '..kind)end
assert(count('MISSION END: orbital_gas_barrage: ready, 1 call; pelican_close_air_support: ready, 1 call; '
    ..'pelican_close_air_support#1 1 kills (1 yours)')==1,lines('MISSION END'))
done()
return 'ok'
''')


    def test_the_loadout_screen_opening_restores_every_stale_carrier_in_its_frame(self):
        self.lua(COMMON + r'''
select_into(0)
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',1);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F7')
tick(30)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=ID22},{id=1298599997}})
tick(80)
mission({host=true})
local record,hud=mission_record({118,118,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
tick(120)
assert(count('READY TO CALL')==2,lines('MISSION'))
assert(W.read(ROW[NAPALM],400)~=native[NAPALM]and W.read(ROW[GATLING],400)~=native[GATLING])
-- The mission ends with its HUD still set up: the restore waits; the loadout screen opens at once: both restored in
-- that frame.
end_mission(h,true)
tick(4)
ship({{type=118},{type=118},{type=22},{type=130}})
tick(1)
assert(W.read(ROW[NAPALM],400)==native[NAPALM]and W.read(ROW[GATLING],400)==native[GATLING],'restored in the frame')
assert(count('LOADOUT OPEN: Orbital Gatling Barrage presentation RESTORED in this frame')==1
    and count('LOADOUT OPEN: Orbital Napalm Barrage presentation RESTORED in this frame')==1,lines('LOADOUT OPEN'))
-- Idempotent: nothing left for the deadline.
tick(60)
assert(count('RETURN TO SHIP')==0,lines('RETURN TO SHIP'))
for kind,bytes in pairs(native)do assert(W.read(ROW[kind],400)==bytes,'not native: '..kind)end
done()
return 'ok'
''')

    def test_a_custom_stratagem_with_no_eligible_carrier_cannot_be_picked_and_the_others_go_on(self):
        # r6 (the user's rule: both directions for every custom stratagem): a custom stratagem whose carrier group has no
        # free member is UNAVAILABLE aboard the ship, and picking it is refused at once (nothing written); before r6 it
        # was picked and refused only at the mission start.
        self.lua(COMMON + r'''
-- The Gas EAT (third in the panel) into slot 0: this world owns no support weapon and no backpack, so the Gas EAT has
-- no carrier: refused. The Pelican CAS into slot 0 instead goes on.
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',0);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F6');press('F7')
tick(30)
assert(count('AVAILABILITY (eat17_gas): UNAVAILABLE: no free member of its carrier group support')==1,lines('AVAILABILITY'))
assert(count('on eat17_gas REFUSED (nothing written): UNAVAILABLE: no free member of its carrier group support')==1,
    lines('REFUSED'))
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',0);SCREEN.set('selecting',true);tick(6)
press('F7');press('F7')
tick(30)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
local V=require('hd2runtime/runtime/stratagem_selector').virtual_slots()
assert(V and V.slots[0].definition=='pelican_close_air_support'and V.slots[1]==nil,
    require('hd2runtime/runtime/stratagem_selector').slots_text(V))
W.saved_loadout({{id=PRECISION_ID},{id=ID22},{id=1298599997}})
tick(80)
assert(count('PRE-MISSION (pelican_close_air_support): READY')==1,lines('PRE-MISSION'))
mission({host=true})
local record,hud=mission_record({118,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
tick(120)
assert(count('MISSION (eat17_gas)')==0,lines('MISSION'))
assert(count('MISSION (pelican_close_air_support): READY TO CALL: loadout slot 0 =')==1,lines('MISSION'))
end_mission(h)
tick(40)
for kind,bytes in pairs(native)do assert(W.read(ROW[kind],400)==bytes,'not native: '..kind)end
done()
return 'ok'
''')


    def test_the_gas_eat_borrows_a_support_carrier_and_its_pod_brings_the_two_bound_launchers(self):
        self.lua(COMMON + r'''
local MG43,EAT17=60,147
native[MG43]=W.read(ROW[MG43],400);native[EAT17]=W.read(ROW[EAT17],400)
-- The pod capture and the impact binding are tested on their own (tests/test_gas_eat.py): here, what the call asks.
local pods=require('hd2runtime/runtime/support_pods')
local captures,binds={},{}
pods.beacon_network=function(world,it)return it and it.entity==7005 and 801 or nil end
pods.capture=function(spec,callback)
    captures[#captures+1]=spec
    callback({kind='pod',pod=8200})
    callback({kind='captured',pod=8200,rack=8201,items={5001,5002},slots={0,1},seconds=6})
    callback({kind='ended'})
    return {status='complete'}
end
require('hd2runtime/runtime/projectile_impact').bind=function(spec,callback)
    binds[#binds+1]=spec
    local h={id=#binds,status='active',from=376,to=82}
    function h.cancel()h.status='cancelled'end
    return h
end
-- The Gas EAT (third in the panel) into slot 0.
SCREEN.set('selecting',false);tick(2)
SCREEN.set('editedSlot',0);SCREEN.set('selecting',true);tick(6)
press('F7');press('F6');press('F6');press('F7')
tick(30)
native_append(22);native_append(130);native_append(41)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22},{id=1298599997},{id=3193297673}})
tick(80)
-- Aboard the ship its panel tile is coloured blue: the EAT-17's support colour set (2), not the red token's (0), which
-- the offensive ones keep.
assert(count('custom icon colours set for eat17_gas on this GUI\'s material instance (the native loadout slot\'s values, '
    ..'colour set 2)')>=1 and count('custom icon colours set for eat17_gas on this GUI\'s material instance (the native '
    ..'loadout slot\'s values, colour set 0)')==0,lines('custom icon colours'))
assert(count('custom icon colours set for pelican_close_air_support on this GUI\'s material instance (the native '
    ..'loadout slot\'s values, colour set 0)')>=1,lines('custom icon colours'))
-- The native loadout slot's overlay takes the same colours: the EAT-17's set for the Gas EAT, the token's for the others.
do
    local OV=require('hd2runtime/runtime/stratagem_slot_overlay')
    local SELM=require('hd2runtime/runtime/stratagem_selector')
    local V1=require('hd2runtime/runtime/virtual_stratagems')
    local world=require('hd2runtime/runtime/event_world').open()
    local eat_kind=OV.colour_type(world,V1.get('eat17_gas'),118)
    local pel_kind=OV.colour_type(world,V1.get('pelican_close_air_support'),118)
    assert(eat_kind==EAT17 and pel_kind==118,'overlay colour types '..tostring(eat_kind)..', '..tostring(pel_kind))
    assert(select(2,SELM.icon_colours(world,eat_kind))==2 and select(2,SELM.icon_colours(world,pel_kind))==0)
end
-- The support policy takes the support weapon: a blue beacon (never an orbital, never the EAT-17 itself).
assert(count('CUSTOM CARRIERS: EAT-17G Gas Expendable Anti-Tank = MG-43 Machine Gun (support, blue beacon); distinct = '
    ..'true')==1,lines('CUSTOM CARRIERS'))
assert(count('PRE-MISSION (eat17_gas): READY: carrier MG-43 Machine Gun (support, blue beacon), code down down right up '
    ..'right')==1,lines('PRE-MISSION'))
mission({host=true})
local record,hud=mission_record({118,22,130,41})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
CT.player(0,0,0)
tick(120)
assert(count('MISSION (eat17_gas): READY TO CALL: loadout slot 0 = MG-43 Machine Gun, presenting as EAT-17G Gas '
    ..'Expendable Anti-Tank; code down down right up right; delivery the vanilla EAT-17 Expendable Anti-Tank pod')==1,
    lines('MISSION'))
-- THE CALL: the MG-43's blue beacon; in its first update its delivery becomes the EAT-17's.
BOMB.set_clock(165760761)
CT.beacon(0,7005,MG43,7,3,12,8,1)
tick()
assert(CT.type_at(0)==EAT17,'the delivery was not redirected: '..CT.type_at(0))
assert(count('eat17_gas#1: beacon 7005 delivery MG-43 Machine Gun -> EAT-17 Expendable Anti-Tank in its first update (1 '
    ..'write, verified true)')==1,lines('eat17_gas#1'))
-- The activation: the capture follows exactly this beacon's pod; the two launchers are bound.
CT.activate(0)
tick(2)
assert(#captures==1 and captures[1].beacon_network==801 and captures[1].type==EAT17
    and captures[1].item_types['80932FA0ED6901D3']and captures[1].label=='eat17_gas#1','the capture')
assert(count('eat17_gas#1: DELIVERED: pod 8200, rack 8201: weapons 5001, 5002')==1,lines('DELIVERED'))
-- Beside them only the mission's barrage watch (the registered Gas Barrage: no source until a native barrage's first
-- shell; tests/test_custom_mp_barrage.py).
local launchers,watches={},{}
for _,spec in ipairs(binds)do
    if spec.accept then watches[#watches+1]=spec else launchers[#launchers+1]=spec end
end
assert(#watches==1 and#watches[1].sources==0 and watches[1].donor=='Orbital Gas Strike','the barrage watch')
assert(#launchers==2 and launchers[1].sources[1]==5001 and launchers[2].sources[1]==5002,'the two launchers bound')
for _,spec in ipairs(launchers)do
    assert(#spec.sources==1 and spec.projectile==132 and spec.donor=='Orbital Gas Strike'and spec.rounds==1
        and spec.entity_type=='80932FA0ED6901D3',spec.label)
end
local inst=require('hd2runtime/api/custom_stratagem').instance_of(5001)
assert(inst and inst.call_id=='eat17_gas#1'and inst.role=='weapon')
assert(require('hd2runtime/api/custom_stratagem').instance_of(8200).role=='pod')
-- No row was written but the carrier's presentation and code: never the EAT-17, its rocket or any donor.
assert(W.read(ROW[EAT17],400)==native[EAT17]and W.read(ROW[41],400)==native[41]and W.read(ROW[118],400)==native[118])
end_mission(h)
tick(40)
for kind,bytes in pairs(native)do assert(W.read(ROW[kind],400)==bytes,'not native: '..kind)end
assert(count('callback failed')==0 and count('failed:')==0,table.concat(logged,' | '))
done()
return 'ok'
''',carriers=EAT_CARRIERS)


if __name__ == '__main__':
    unittest.main()
