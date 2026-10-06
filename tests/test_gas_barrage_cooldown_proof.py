"""proof/GasBarrageCooldownProof 0.1.0, the fixed 60 s cooldown (docs/custom-stratagems.md, "The fixed cooldown"): a
companion of GasBarragePayloadProof 0.2.2 (unchanged). Offline, both proofs' own addons end to end on the event world:
the payload proof discovers, presents, converts and pays the Gas Barrage exactly as before; when the game starts the
converted slot's cooldown, the cooldown proof's runtime/slot_cooldown.lua watch gives it 60 s from the call-in's arrival,
for the 380mm and then, with the 380mm in the loadout, for the Napalm, and the carriers' rows (their own 240 s) are never
written."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD, PROOF
from test_stratagem_slot_conversion import SLOT
from test_gas_barrage_mission_proof import HARNESS
from test_gas_barrage_payload_proof import FLOW3, PAYLOAD_FLOW, addon as payload_addon

FOLDER = ROOT / 'proof/GasBarrageCooldownProof'

COOLDOWN_FLOW = r"""
local function cool_proof()assert(loadstring(COOL_ADDON,'@'..COOL_RESOURCE))()end
local US=1000000
local CLOCK=165760761
local function put64(at,n)W.write(at,W.u32(n%4294967296)..W.u32(math.floor(n/4294967296)))end
local function u64_at(at)local s=W.read(at,8);return b.u32(s,0)+b.u32(s,4)*4294967296 end
local function entry_at(h)return h.record+0x38+0x188+2*0x30 end
-- The game's call of the converted entry 2: an activation, an arrival `inbound` s later and the carrier's own end
-- (240 s x 0.855) after the arrival.
local function call(h,at,inbound)
    local arrival=at+math.floor(inbound*US)
    put64(entry_at(h)+0x10,at);put64(entry_at(h)+0x20,arrival);put64(entry_at(h)+0x18,arrival+205200000)
    return arrival
end
local CD=require('hd2runtime/domains/slot_cooldown')
local function hud_cooling(h,total)
    local slot=h.slots[2].address
    local bar=slot+CD.hud.bar
    W.write(bar+CD.hud.barIndex,W.u32(2));W.write(bar+CD.hud.barState,W.u32(CD.hud.cooling))
    W.write(bar+CD.hud.barTotal,b.encode(total,'f32'));W.write(slot+CD.hud.coolingLeft,b.encode(total,'f32'))
end
"""


def cooldown_addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class GasBarrageCooldownProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = payload_addon()
        cool_resource, cool_wrapped = cooldown_addon()
        self.assertEqual(cool_resource, 'mods/skyeshade/hd2runtime_gas_barrage_cooldown_proof')
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(wrapped) + '\nlocal RESOURCE='
            + lua_literal(resource) + '\nlocal COOL_ADDON=' + lua_literal(cool_wrapped) + '\nlocal COOL_RESOURCE='
            + lua_literal(cool_resource) + PROOF + HARNESS + FLOW3 + PAYLOAD_FLOW + COOLDOWN_FLOW + body), b'ok')

    def test_the_proof_sources(self):
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8')
        for forbidden in ('VirtualProtect', 'WriteProcessMemory', 'ffi', 'windows_write', '.write('):
            self.assertNotIn(forbidden, body)
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        self.assertIn("local BUILD='0.1.0 FIXED COOLDOWN'", body)
        self.assertNotIn('cool.arm({definition=DEFINITION,seconds=SECONDS,from=from,carrier', body)

    def test_each_call_gets_sixty_seconds_whichever_carrier_and_the_carriers_rows_are_never_written(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
local NATIVE_ROWS={}
for _,kind in ipairs({125,106,127})do NATIVE_ROWS[kind]=W.read(ROW[kind],400)end
local token_row=W.read(ROW118,400)
cool_proof()
to_mission()
-- Aboard the ship, before any conversion: the compatible carriers' own cooldowns, read-only.
assert(count('COOLDOWN: carrier native cooldowns before any conversion (the payload-compatible carriers\' own rows, '
    ..'read-only): Orbital 380mm HE Barrage 240.00 s (cooldown type 0); Orbital Napalm Barrage 240.00 s (cooldown type '
    ..'0); Orbital Walking Barrage 240.00 s (cooldown type 0); the Gas Barrage cooldown will be 60.0 s whichever is '
    ..'discovered')==1,table.concat(logged,' | '))
-- MISSION 1: the 380mm carries the Gas Barrage.
local h=start_mission()
tick(64)
assert(count('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital 380mm HE Barrage')==1,
    table.concat(logged,' | '))
assert(count('MISSION START: the fixed cooldown is armed: 60.0 s from the call-in\'s arrival')==1
    and count('COOLDOWN: the Gas Barrage conversion is seen: loadout slot 0 = record entry 2 -> the carrier Orbital '
    ..'380mm HE Barrage (type 125, stable id 3108516875). COOLDOWN: carrier native = 240.00 s (its row, never written; '
    ..'cooldown type 0: the entry\'s own)')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
local arrival=call(h,CLOCK-300000,6)
tick(2)
assert(count('COOLDOWN: carrier native = 240.00 s (Orbital 380mm HE Barrage\'s row; with the game\'s modifiers x0.8550 '
    ..'that is 205.20 s)')==1,table.concat(logged,' | '))
assert(count(('COOLDOWN: game started = 205.20 s after the call-in\'s arrival (record entry 2, loadout slot 0: activation '
    ..'t=%d, arrival t=%d, 6.00 s inbound, end t=%d; seen 0.30 s after the activation, at t=%d, 210.90 s left)'):format(
    CLOCK-300000,arrival,arrival+205200000,CLOCK))==1,table.concat(logged,' | '))
assert(count(('COOLDOWN: Gas Barrage override = 60.0 s from the call-in\'s arrival (end t=%d -> t=%d; 1 write; the '
    ..'entry reads it true, nothing else of the record changed true, non-target bytes unchanged true, protection '
    ..'restored true)'):format(arrival+205200000,arrival+60*US))==1,table.concat(logged,' | '))
assert(count(('COOLDOWN: verified end = current_game_time + 65.70 (t=%d at the write; the entry\'s end t=%d = the '
    ..'call-in\'s arrival + 60.00 = the activation + 66.00)'):format(CLOCK,arrival+60*US))==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes+1 and u64_at(entry_at(h)+0x18)==arrival+60*US)
-- The HUD's first cooling frame, then the slot available again 60 s after the arrival.
BOMB.set_clock(arrival+400000);hud_cooling(h,59.6);tick(2)
assert(count('COOLDOWN: HUD: the slot is COOLING; its bar took a total of 59.60 s on its first cooling frame')==1
    and count('-> the HUD shows the Gas Barrage cooldown')==1,table.concat(logged,' | '))
BOMB.set_clock(arrival+30*US);tick(4)
assert(count('COOLDOWN: +30.00 s after the arrival: 30.00 s left on the entry; the HUD slot state 4')==1,
    table.concat(logged,' | '))
BOMB.set_clock(arrival+60*US);tick(2)
assert(count(('COOLDOWN: READY AGAIN: record entry 2 (loadout slot 0) is callable again at t=%d: 60.00 s after the '
    ..'call-in\'s arrival, 66.00 s after the activation, 65.70 s after the write; final cooldown = 60.00 s from the '
    ..'arrival (the carrier\'s own would have lasted 145.20 s more)'):format(arrival+60*US))==1,table.concat(logged,' | '))
end_mission(h)
tick(16)
assert(count('MISSION END: the record\'s cooldown ends are mission state the game rebuilds: nothing to restore')==1
    and count('COOLDOWN: watch ended:')==1,table.concat(logged,' | '))
for kind,row in pairs(NATIVE_ROWS)do assert(W.read(ROW[kind],400)==row,'carrier row '..kind..' written')end
assert(W.read(ROW118,400)==token_row)
-- MISSION 2: the 380mm picked natively into slot 3: the Napalm carries the Gas Barrage, 5 s inbound; again 60 s.
BOMB.set_clock(CLOCK)
ship({{type=118},{type=41},{type=22},{type=130}});tick(4)
W.write(SCREEN.record+SEL.loadout.entries+3*SEL.loadout.entryStride+SEL.loadout.entryType,W.u32(125));repaint();tick(4)
SCREEN.close();tick(8)
W.saved_loadout({{id=PRECISION_ID},{id=3193297673},{id=ID22},{id=BIG380_ID}})
mission({host=true})
local record,hud=mission_record({118,41,22,125})
h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
tick(64)
assert(count('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital Napalm Barrage')==1
    and count('COOLDOWN: carrier native = 240.00 s (its row, never written')==2,table.concat(logged,' | '))
writes=#W.runtime.writes
arrival=call(h,CLOCK-200000,5)
tick(2)
assert(count('COOLDOWN: Gas Barrage override = 60.0 s from the call-in\'s arrival')==2
    and u64_at(entry_at(h)+0x18)==arrival+60*US and#W.runtime.writes==writes+1,table.concat(logged,' | '))
BOMB.set_clock(arrival+60*US);tick(2)
assert(count('final cooldown = 60.00 s from the arrival')==2,table.concat(logged,' | '))
-- In the mission the Napalm's row holds the Gas Barrage look (the payload proof's); its cooldown members are its own.
for kind,row in pairs(NATIVE_ROWS)do
    local now=W.read(ROW[kind],400)
    assert(now:sub(0x69,0x70)==row:sub(0x69,0x70)and now:sub(0x95,0x98)==row:sub(0x95,0x98),'cooldown of '..kind)
end
assert(count('REFUSED')==0 and count('callback failed')==0 and count('TEST REFUSED')==0,table.concat(logged,' | '))
end_mission(h)
tick(16)
for kind,row in pairs(NATIVE_ROWS)do assert(W.read(ROW[kind],400)==row,'carrier row '..kind..' written')end
assert(W.read(ROW118,400)==token_row)
done()
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
