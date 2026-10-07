"""Other players' custom picks on the loadout screen (display only; runtime/stratagem_slot_overlay.lua remote_panels and
remote_slots; research/peer-messaging-F5FEE03DCFDB.json "panels"; research/docs/runtime-peer-messaging-F5FEE03DCFDB.md
sections 13 and 14), on the offline loadout screen of tests/test_stratagem_slot_overlay.py with a teammate panel laid out
as the research found it (panel k = ui + 0x53A78 + k * 0x1EE18; its peer, its record; the slot panel +0x5B78 with its
bound record, local flag and slot widgets). THE SYNCED TABLE IS THE AUTHORITY (live 2026-10-04: aboard the ship every
teammate widget read type 0, the game had not sent that player's slots): a teammate slot whose synced custom id is
registered here gets the id's icon on its icon box whatever the native widget shows (empty, the token, another type),
when its panel is conclusively that player's and the box is visible. A slot that cannot be placed logs REMOTE OVERLAY
REFUSED: peer, slot, reason. A changed pick, a player leaving, an incompatible player, a faded panel, a closed screen or
changed code leave (or put back) the native slot. Nothing is written; the teammate's record is never touched."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT
from test_stratagem_slot_overlay import OVERLAY

RESEARCH = json.loads((ROOT / 'research/peer-messaging-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

REMOTE = r"""
local PN=require('hd2runtime/domains/peer_messaging').panels
for _,pin in ipairs(PN.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
overlay.reset_panels_for_tests()
local L,I=SEL.loadout,SEL.slotIcon
local ME,THEM='1111222233334444','5555666677778888'
W.players({{peer=ME,avatar=100},{peer=THEM}},ME)
local function peer8(hex)return b.unhex(hex):reverse()end
-- Panel k's peer binding only (the game binds panel 0 to this machine's player).
local function bind(k,peer)W.write(SCREEN.ui+PN.base+k*PN.stride+PN.peer,peer and peer8(peer)or string.rep('\0',8))end
-- Teammate panel k bound to `peer` (its UI record k, owner = the peer), its widgets showing `types`. Each slot's icon box
-- (the widget's background element) is laid out on screen; a type-0 widget's icon element is cleared as the game clears
-- it (no primitive, alpha 0): the overlay never reads it.
local function teammate(k,peer,types)
    local ui=SCREEN.ui
    local panel=ui+PN.base+k*PN.stride
    local record=ui+L.records+k*L.recordStride
    local slot_panel=panel+PN.slotPanel
    W.write(panel+PN.peer,peer and peer8(peer)or string.rep('\0',8))
    W.write(panel+PN.record,W.u64(record))
    W.write(slot_panel+PN.boundRecord,W.u64(record))
    W.write(slot_panel+PN.localFlag,string.char(0))
    W.write(record+PN.recordOwner,peer and peer8(peer)or string.rep('\0',8))
    local out={}
    for s=0,3 do
        local w=slot_panel+PN.widgets+s*PN.widgetStride
        W.write(w+PN.widgetType,W.u32(types[s+1]or 0))
        place(w+O.background,600+80*s,300,48,48)
        if(types[s+1]or 0)==0 then
            W.write(w+I.element+O.primitive,W.u32(4294967295));W.write(w+I.element+O.alpha,W.f32(0))
        else place(w+I.element,600+80*s,300,48,48)end
        out[s]=w
    end
    return out,record
end
local SYNCED={}
local function source()return next(SYNCED)and SYNCED or nil end
local _ship=ship
ship=function()_ship();bind(0,ME)end
local function refusals(text)return count('REMOTE OVERLAY REFUSED: '..text)end
"""


class RemotePanelResearchTests(unittest.TestCase):
    def test_the_panel_research_and_its_domain(self):
        p = RESEARCH['panels']
        self.assertEqual((p['base'], p['stride'], p['count'], p['peer'], p['record'], p['slotPanel']),
            (0x53A78, 0x1EE18, 4, 0x1EE00, 0x1EDF0, 0x5B78))
        self.assertEqual((p['boundRecord'], p['localFlag'], p['widgets'], p['widgetStride'], p['widgetType'],
            p['recordOwner']), (0xD960, 0xD978, 0x8EC0, 0x12A8, 0x128C, 0x9E8))
        # Panel 0's slot panel and widgets are exactly the selector research's (already live-proven for the local player).
        ui = json.loads((ROOT / 'research/runtime-stratagem-ui-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        lo = ui['layout']['loadoutUi']
        self.assertEqual(p['base'] + p['slotPanel'], ui['layout']['slotFocus']['panel'])
        self.assertEqual(p['base'] + p['slotPanel'] + p['widgets'], lo['panel0Widgets'])
        self.assertEqual(p['base'] + p['slotPanel'] + p['boundRecord'], lo['panel0BoundRecord'])
        self.assertEqual((p['widgetStride'], p['recordOwner']), (lo['widgetStride'], lo['owner']))
        rvas = {pin['rva'] for pin in p['pins']}
        for rva in (0x1466AE2, 0x146CC5A, 0x189CA55, 0x189C900, 0x14706AF, 0x1896340, 0x1893613):
            self.assertIn(rva, rvas)


class RemoteOverlayTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SELECT + OVERLAY + REMOTE + body + "\nreturn 'ok'"), b'ok')

    def test_a_synced_pick_is_drawn_even_when_the_teammate_slot_is_empty_and_nothing_is_written(self):
        self.check(r"""
ship()
local before=native_bytes()
-- The live case: the teammate's panel is bound, every widget type 0 (no slot sent yet).
local widgets,record=teammate(1,THEM,{0,0,0,0})
local record_bytes=W.read(record,L.recordStride)
local world=assert(world_module.open())
local list=assert(overlay.remote_panels(world))
assert(#list==1 and list[1].k==1 and list[1].peer==THEM and list[1].widgets[0].type==0)
SYNCED[THEM]={[0]='orbital_gas_barrage',[1]='zzz_not_registered_here',[2]=false,[3]='orbital_gas_barrage'}
local S=overlay.remote_slots(source)
tick()
local gui
for k,c in ipairs(calls)do if c.name=='create_screen_gui'then gui=k end end
local bm=bitmaps_of(gui)
assert(#bm==2 and bm[1].args[2]==images.material_name(ICON)and bm[2].args[2]==images.material_name(ICON),
    'two overlays: slot 0 and slot 3 '..#bm)
assert(at_xy(bm[1],600,300,48,48)and at_xy(bm[2],840,300,48,48),'on each slot\'s icon box')
assert(count('OVERLAY: 2 icons drawn over native slot icons')==1 and count('remote '..THEM..' slot 0 (orbital_gas_barrage, '
    ..'panel 1) at 600, 300, 48 x 48')==1,table.concat(logged,' | '))
-- The slot it cannot place, once, with its reason; nothing for the vanilla slot.
assert(refusals('peer '..THEM..', slot 1, reason zzz_not_registered_here is not registered here')==1
    and refusals('peer '..THEM..', slot 2')==0 and refusals('peer '..THEM..', slot 0')==0,table.concat(logged,' | '))
tick();tick()
assert(refusals('peer '..THEM..', slot 1')==1,'logged once per reason')
-- The native slot showing the token or another native type: the synced id is still the authority.
W.write(widgets[0]+PN.widgetType,W.u32(118));W.write(widgets[3]+PN.widgetType,W.u32(22))
tick()
assert(#bitmaps_of(gui)==2 and count('overlays removed')==0)
-- Display only: no write, the native widgets and the teammate's record untouched.
assert(#W.runtime.writes==0 and W.read(record,L.recordStride)==record_bytes)
local after=native_bytes()
for k=0,3 do assert(after[k]==before[k])end
S.stop()
""")

    def test_every_change_clears_or_updates_the_overlay(self):
        self.check(r"""
ship()
local widgets=teammate(1,THEM,{0,0,0,0})
SYNCED[THEM]={[0]='orbital_gas_barrage'}
local S=overlay.remote_slots(source)
tick()
assert(count('OVERLAY: 1 icon')==1)
-- The teammate's pick moves to slot 1: the overlay follows the new state.
SYNCED[THEM]={[1]='orbital_gas_barrage'}
tick()
assert(count('the native icons untouched): remote '..THEM..' slot 1 (orbital_gas_barrage, panel 1)')==1,
    table.concat(logged,' | '))
-- Cleared: no custom pick left (nothing is read then).
SYNCED[THEM]=nil
tick()
assert(count('overlays removed')==1)
-- Back; then the panel fades (the stratagem grid open): its icon box is transparent, the overlay goes, once logged.
SYNCED[THEM]={[0]='orbital_gas_barrage'}
tick()
W.write(widgets[0]+O.background+O.alpha,W.f32(0))
tick();tick()
assert(count('overlays removed')==2 and refusals('peer '..THEM..', slot 0, reason the slot is not visible: its icon box '
    ..'is transparent')==1,table.concat(logged,' | '))
W.write(widgets[0]+O.background+O.alpha,W.f32(1))
tick()
assert(count('OVERLAY: 1 icon')==4)
-- The player leaves the panel (unbound: peer 0) while its synced pick is still known.
teammate(1,nil,{0,0,0,0})
tick()
assert(count('overlays removed')==3 and refusals('peer '..THEM..', slot 0, reason no panel of the loadout screen is bound '
    ..'to this player')==1,table.concat(logged,' | '))
-- The panel is bound again: drawn again.
teammate(1,THEM,{0,0,0,0})
tick()
assert(count('OVERLAY: 1 icon')==5,table.concat(logged,' | '))
-- The player is no longer compatible (its synced slots are no longer given).
SYNCED={}
tick()
assert(count('overlays removed')==4)
SYNCED[THEM]={[0]='orbital_gas_barrage'}
tick()
-- The loadout screen closes.
SCREEN.close();tick()
assert(count('overlays removed')==5)
S.stop()
assert(#W.runtime.writes==0)
""")

    def test_panels_are_mapped_by_their_own_peer_binding_whatever_their_index(self):
        self.check(r"""
ship()
-- The teammate on panel 0 and this machine's player on panel 2 (no index or role assumption).
bind(0,nil)
teammate(0,THEM,{0,0,0,0})
bind(2,ME)
SYNCED[THEM]={[1]='orbital_gas_barrage'}
local S=overlay.remote_slots(source)
tick()
assert(count('REMOTE OVERLAY MAP: panel 0 -> peer '..THEM..' (a teammate; record owner '..THEM..', local flag 0), '
    ..'panel 1 -> none, panel 2 -> peer '..ME..' (this machine')==1,table.concat(logged,' | '))
assert(count('REMOTE OVERLAY DRAWN: panel 0, peer '..THEM..', slot 1: orbital_gas_barrage at 680, 300, 48 x 48 (the native '
    ..'slot shows type 0)')==1,table.concat(logged,' | '))
-- Logged once per open, and once per placement.
tick();tick()
assert(count('REMOTE OVERLAY MAP:')==1 and count('REMOTE OVERLAY DRAWN:')==1)
-- The teammate's record names another owner (not sent yet): its peer binding decides; the map reports the owner.
local _,record=teammate(0,THEM,{0,0,0,0})
W.write(record+PN.recordOwner,string.rep('\0',8))
tick()
assert(count('REMOTE OVERLAY MAP:')==2 and count('record owner 0000000000000000')==1 and count('OVERLAY: 1 icon')==1,
    table.concat(logged,' | '))
-- The screen closes and opens again: the map is logged again.
SCREEN.close();tick()
SCREEN=W.loadout_screen({entries={{type=136},{type=118},{type=22},{type=41}},selecting=false});SCREEN.frame()
for k=0,3 do place(SCREEN.element(k),100+80*k,900,64,64)end
bind(2,ME);teammate(0,THEM,{0,0,0,0})
tick()
assert(count('REMOTE OVERLAY MAP:')==3,table.concat(logged,' | '))
-- One player bound to two panels: ambiguous, never drawn.
teammate(3,THEM,{0,0,0,0})
tick()
assert(count('REMOTE OVERLAY REFUSED: peer '..THEM..', slot 1, reason its loadout panel ')==1 and count('is not usable: this '
    ..'player is bound to more than one panel')==1 and count('OVERLAY: 1 icon')==2,table.concat(logged,' | '))
S.stop()
assert(#W.runtime.writes==0)
""")

    def test_changed_code_and_no_synced_pick_draw_nothing(self):
        self.check(r"""
ship()
teammate(1,THEM,{0,0,0,0})
-- No compatible teammate: nothing is read, nothing drawn, nothing logged.
local S=overlay.remote_slots(source)
tick()
assert(#bitmaps_of(#calls+1)==0 and count('OVERLAY')==0)
S.stop()
-- A compatible teammate without a custom pick: the map only, nothing drawn.
SYNCED[THEM]={[0]=false,[1]=false}
S=overlay.remote_slots(source)
tick()
assert(count('REMOTE OVERLAY MAP:')==1 and count('OVERLAY:')==0 and count('DRAWN')==0,table.concat(logged,' | '))
S.stop()
-- A changed pin: refused, nothing drawn.
SYNCED[THEM]={[0]='orbital_gas_barrage'}
local pin=PN.pins[1]
W.write(W.GAME+pin.rva,string.char(0xCC))
overlay.reset_panels_for_tests()
local world=assert(world_module.open())
local list,why=overlay.remote_panels(world)
assert(list==nil and why:find('changed',1,true),tostring(why))
S=overlay.remote_slots(source)
tick()
assert(count('OVERLAY:')==0)
S.stop()
""")


if __name__ == '__main__':
    unittest.main()
