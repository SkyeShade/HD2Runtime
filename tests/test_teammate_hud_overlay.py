"""Other players' custom slots on the in-mission teammate stratagem HUD (display only; runtime/stratagem_slot_overlay.lua
teammate_cards and mission_remote_slots; research/teammate-hud-F5FEE03DCFDB.json;
docs/research/teammate-hud-F5FEE03DCFDB.md), on the offline mission HUD of tests/test_stratagem_slot_overlay.py with the
squad container laid out as the research found it (panel k = HUD + 0x24E340 + 0x1F8C8 + 0x6A0 + k * 0xA6A0, bound to its
player by the entity at +0xA66C; card j = panel + 0x2A20 + j * 0x14F0: its record entry index, the type it shows, its
state, its lit band, its icon element at +0x518).

A card shows this machine's copy of that player's record entry, which still holds the token (Orbital Precision Strike)
while its owner's Runtime has converted only its own copy. THE MISSION'S FROZEN SYNCED TABLE IS THE AUTHORITY: a card
gets the custom icon only when the table names a custom id for that player's loadout slot and the card shows that id's
token or frozen carrier; a real Precision Strike, a vanilla slot and this player's own HUD are never touched. Nothing is
written."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT
from test_stratagem_slot_overlay import OVERLAY

RESEARCH = json.loads((ROOT / 'research/teammate-hud-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

TEAM = r"""
local TH=require('hd2runtime/domains/teammate_hud')
local THL=TH.layout
for _,pin in ipairs(TH.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
overlay.reset_panels_for_tests()
local RC=require('hd2runtime/domains/stratagem_calldown').hud.records
local ME,THEM,OTHER='1111222233334444','5555666677778888','9999AAAABBBBCCCC'
local function peer8(hex)return b.unhex(hex):reverse()end
mission({host=true})
local HUD=W.stratagem_hud({peer=ME,slots={{type=136,code={}},{type=41,code={}}},record={{type=136},{type=41}}})
-- The player list: this machine's player (entity 10), THEM (11), OTHER (12).
W.players({{peer=ME,avatar=100},{peer=THEM},{peer=OTHER}},ME)
local RECORDS=b.pointer(W.read(W.GAME+RC.global,8),0)
-- Record k of this machine's records: `peer`'s copy, its entries {type, granted}.
local function record(k,peer,entries)
    local at=RECORDS+k*RC.stride
    W.write(at,peer8(peer))
    for i,e in ipairs(entries)do
        local entry=at+RC.entries+(i-1)*RC.entryStride
        W.write(entry,W.u32(e.type));W.write(entry+9,string.char(e.granted or 0))
    end
    W.write(at+RC.entryCount,W.u32(#entries))
    if b.u32(W.read(RECORDS+RC.count,4),0)<k+1 then W.write(RECORDS+RC.count,W.u32(k+1))end
    return at
end
local CONTAINER=HUD.hud+THL.missionHud+THL.container
local function card_of(k,j)return CONTAINER+THL.panels+k*THL.panelStride+THL.cards+j*THL.cardStride end
local function icon_of(k,j)return card_of(k,j)+THL.cardIcon end
-- Every card not drawn (as the game leaves them while the stratagem key is not held).
local function hide(k)for j=0,3 do W.write(icon_of(k,j)+O.primitive,W.u32(4294967295));W.write(icon_of(k,j)+O.alpha,W.f32(0))end end
for k=0,2 do hide(k)end
-- Teammate panel k bound to `entity`, its cards {entry, type, state, lo, hi} drawn 60 px apart.
local function panel(k,entity,cards)
    W.write(CONTAINER+THL.panels+k*THL.panelStride+THL.panelEntity,W.u32(entity))
    for j=0,3 do
        local c,card=cards[j+1],card_of(k,j)
        if c then
            W.write(card+THL.cardEntry,W.u32(c.entry));W.write(card+THL.cardType,W.u32(c.type))
            W.write(card+THL.cardState,W.u32(c.state or 1))
            W.write(card+THL.bandStart,W.f32(c.lo or 0));W.write(card+THL.bandEnd,W.f32(c.hi or 1))
            W.write(icon_of(k,j)+O.primitive,W.u32(700+j))
            place(icon_of(k,j),1500+60*j,800-100*k,48,48)
        else
            W.write(icon_of(k,j)+O.primitive,W.u32(4294967295));W.write(icon_of(k,j)+O.alpha,W.f32(0))
        end
    end
end
-- THEM's record copy here: four loadout picks (Precision Strike in slot 1 and slot 3, a granted entry between) .
local THEIRS=record(1,THEM,{{type=136},{type=118},{type=130,granted=1},{type=22},{type=118}})
-- Its cards: entries 0, 1, 3 and 4 (loadout slots 0-3).
local function their_cards(over)
    local c={{entry=0,type=136},{entry=1,type=118},{entry=3,type=22},{entry=4,type=118}}
    for j,v in pairs(over or{})do c[j]=v end
    return c
end
local SYNCED,CARRIERS={},{[41]='orbital_gas_barrage'}
local function source()if next(SYNCED)then return SYNCED,CARRIERS end end
local function refusals(text)return count('TEAMMATE HUD OVERLAY REFUSED: '..text)end
local function drawn_lines(text)return count('TEAMMATE HUD OVERLAY DRAWN: '..(text or''))end
local function gui_of()local g;for k,c in ipairs(calls)do if c.name=='create_screen_gui'then g=k end end;return g end
local function rects_of(g)local out={};for _,c in ipairs(of('rect'))do if c.args[1]==g then out[#out+1]=c end end;return out end
local function at_hud(c,x,y,w,h)
    return c.args[3][1]==x and c.args[3][2]==y and c.args[3][3]==O.hudOverlayLayer and c.args[4][1]==w and c.args[4][2]==h
end
"""


class TeammateHudResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        layout = RESEARCH['layout']
        self.assertEqual((layout['container'], layout['panels'], layout['panelStride'], layout['panelCount'],
            layout['panelEntity']), (0x1F8C8, 0x6A0, 0xA6A0, 3, 0xA66C))
        self.assertEqual((layout['cards'], layout['cardStride'], layout['cardCount'], layout['cardEntry'],
            layout['cardType'], layout['cardIcon'], layout['cardState'], layout['bandStart'], layout['bandEnd']),
            (0x2A20, 0x14F0, 4, 0x14B8, 0x14C8, 0x518, 0x14CC, 0x14D4, 0x14DC))
        pins = {pin['rva']: pin['asm'] for group in RESEARCH['proofs'].values() for pin in group}
        self.assertEqual(pins[0x12EBECA], 'lea rcx, [r14 + 0x1f8c8]')                     # the squad container
        self.assertEqual(pins[0x182F6EB], 'mov dword ptr [r14 + 0xa66c], r8d')           # the panel's player entity
        self.assertEqual(pins[0x183A053], 'mov edx, dword ptr [r9 + r12*8 + 0x188]')     # the card's entry type
        self.assertEqual(pins[0x183A1EC], 'lea rdi, [rsi + 0x518]')                       # the card's icon element
        self.assertEqual(pins[0x183ACE5], 'movss dword ptr [rcx + 0x14dc], xmm0')        # the lit band's end
        # The local HUD's cards (the same class): background, frame and icon are one quad; ready cards fully lit.
        cards = [c for o in RESEARCH['observations'] for c in o['localCards']]
        self.assertTrue(any(c['stack']['icon']['drawn'] for c in cards))
        self.assertTrue(all(c['band'] == [0.0, 1.0] for c in cards if c['state'] == 1))
        # The panel's player list is the event world's (the same manager, peers and descriptors).
        self.assertEqual(run(r'''
local P=require('hd2runtime/domains/event_natives').players
local D=require('hd2runtime/domains/teammate_hud')
local proven={}
for _,pin in ipairs(D.pins)do proven[pin.rva]=true end
assert(P.global==0x3326468 and P.peers==0x2C8 and P.peerStride==0x38 and P.descriptors==0xE8 and P.descriptorEntity==8)
assert(proven[0x182F6CE]and proven[0x182F708]and proven[0x182F710])
assert(D.layout.hudSystem==require('hd2runtime/domains/stratagem_selector').slotOverlay.hudRoot)
return 'ok'
'''), b'ok')

    @unittest.skipUnless((ROOT / 'research/teammate-hud-F5FEE03DCFDB.json').is_file(), 'research absent')
    def test_the_domain_is_current(self):
        import generate_teammate_hud
        self.assertEqual(generate_teammate_hud.generate(check=True), [])


class TeammateHudOverlayTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SELECT + OVERLAY + TEAM + body + "\nreturn 'ok'"), b'ok')

    def test_a_custom_slot_is_drawn_over_the_token_and_nothing_else_is_touched(self):
        self.check(r"""
panel(0,11,their_cards())
local before=W.read(THEIRS,RC.stride)
local cards_before=W.read(card_of(0,0),4*THL.cardStride)
-- THEM's table: slot 1 is the custom stratagem, slot 3 is a REAL Precision Strike (the same type on its card).
SYNCED[THEM]={[0]=false,[1]='orbital_gas_barrage',[2]=false,[3]=false}
local S=overlay.mission_remote_slots(source)
tick()
local g=gui_of()
assert(g and of('create_screen_gui')[1].args[1]==UW,'a Ui World GUI')
local bm=bitmaps_of(g)
assert(#bm==1 and bm[1].args[2]==images.material_name(ICON),'one overlay: '..#bm)
assert(at_hud(bm[1],1560,800,48,48),'on card 1\'s icon quad at the HUD overlay layer')
assert(drawn_lines('panel 0, peer '..THEM..', slot 1 (record entry 1): orbital_gas_barrage over the card showing type 118 '
    ..'(its token), at 1560, 800, 48 x 48; display only')==1,table.concat(logged,' | '))
-- The plate (the native slot grey) under it; the shade above it is empty (ready: lit 0..1).
local r=rects_of(g)
assert(#r==3,'plate and two shade bands '..#r)
assert(r[1].args[2][3]==O.hudOverlayLayer-1 and r[1].args[4][2]==O.backgroundGrey,'the plate')
assert(r[2].args[2][3]==O.hudOverlayLayer+1 and r[2].args[3][2]==0 and r[3].args[3][2]==0,'no shade while ready')
-- Quiet: no OVERLAY line; repeated frames log nothing new.
tick();tick()
assert(count('slot overlay OVERLAY:')==0 and drawn_lines()==1 and refusals('')==0,table.concat(logged,' | '))
-- Display only.
assert(#W.runtime.writes==0 and W.read(THEIRS,RC.stride)==before and W.read(card_of(0,0),4*THL.cardStride)==cards_before)
S.stop()
""")

    def test_the_cooldown_band_is_followed_and_showing_hiding_is_silent(self):
        self.check(r"""
panel(0,11,their_cards())
SYNCED[THEM]={[1]='orbital_gas_barrage'}
local S=overlay.mission_remote_slots(source)
tick()
local g=gui_of()
-- Cooling: the card lights 0..0.25 of its height (from its top); the shade covers the rest (the bottom 0.75).
W.write(card_of(0,1)+THL.cardState,W.u32(4));W.write(card_of(0,1)+THL.bandEnd,W.f32(0.25))
tick()
local u=of('update_rect')
local last=u[#u]
assert(last.args[3][2]==800 and math.abs(last.args[4][2]-36)<1e-6 and last.args[5][1]==math.floor(255*overlay.SHADE+0.5),
    'the bottom band shaded')
-- Unavailable: nothing lit, all shaded.
W.write(card_of(0,1)+THL.bandEnd,W.f32(0))
tick()
u=of('update_rect')
assert(math.abs(u[#u].args[4][2]-48)<1e-6)
-- Released (the stratagem key): the cards are not drawn; nothing is logged; held again: drawn again, not re-logged.
hide(0)
tick()
assert(#of('destroy_gui')==1 and count('overlays removed')==0)
panel(0,11,their_cards())
tick();hide(0);tick();panel(0,11,their_cards());tick()
assert(#of('create_screen_gui')==3 and drawn_lines()==1 and refusals('')==0,table.concat(logged,' | '))
S.stop()
assert(#W.runtime.writes==0)
""")

    def test_the_carrier_a_resent_record_holds_is_drawn_too_and_anything_else_is_refused(self):
        self.check(r"""
SYNCED[THEM]={[1]='orbital_gas_barrage'}
-- The owner's game sent its converted record: the card shows the frozen carrier (type 41).
panel(0,11,their_cards({[2]={entry=1,type=41}}))
local S=overlay.mission_remote_slots(source)
tick()
assert(#bitmaps_of(gui_of())==1 and drawn_lines('panel 0, peer '..THEM..', slot 1 (record entry 1): orbital_gas_barrage over '
    ..'the card showing type 41 (its carrier)')==1,table.concat(logged,' | '))
-- Another type (a desync): refused once, the native card stays.
panel(0,11,their_cards({[2]={entry=1,type=33}}))
tick();tick()
assert(#of('destroy_gui')==1 and refusals('peer '..THEM..', slot 1, reason the card shows type 33, neither '
    ..'orbital_gas_barrage\'s token (type 118) nor its frozen carrier (type 41); the native card stays')==1,
    table.concat(logged,' | '))
-- An id not registered here.
SYNCED[THEM]={[1]='zzz_not_here'}
panel(0,11,their_cards())
tick()
assert(refusals('peer '..THEM..', slot 1, reason zzz_not_here is not registered here (the native card stays)')==1)
S.stop()
assert(#W.runtime.writes==0)
""")

    def test_panels_are_bound_by_their_own_player_and_the_table_ends_with_the_mission(self):
        self.check(r"""
-- OTHER is on panel 0 (no custom pick), THEM on panel 2: bound by entity, whatever the index.
local OTHERS=record(2,OTHER,{{type=118},{type=136}})
panel(0,12,{{entry=0,type=118},{entry=1,type=136}})
panel(2,11,their_cards())
SYNCED[THEM]={[3]='orbital_gas_barrage'}
SYNCED[OTHER]={[0]=false,[1]=false}
local S=overlay.mission_remote_slots(source)
tick()
local bm=bitmaps_of(gui_of())
-- THEM's slot 3 (card 3 of panel 2) only; OTHER's real Precision Strike (slot 0) stays native.
assert(#bm==1 and at_hud(bm[1],1680,600,48,48),table.concat(logged,' | '))
assert(drawn_lines('panel 2, peer '..THEM..', slot 3 (record entry 4)')==1,table.concat(logged,' | '))
-- An unbound panel (the invalid entity) or a player not in the list: nothing.
panel(2,0,their_cards())
tick()
assert(#of('destroy_gui')==1,'unbound: removed')
panel(2,11,their_cards())
tick()
-- The mission ends (custom multiplayer not running: no table): removed, and the next mission logs again.
SYNCED={}
tick()
assert(#of('destroy_gui')==2,'no table: removed')
SYNCED[THEM]={[3]='orbital_gas_barrage'}
tick()
assert(drawn_lines('panel 2, peer '..THEM..', slot 3')==2,table.concat(logged,' | '))
-- No table again (a solo mission, or custom multiplayer refused): nothing is drawn.
SYNCED={}
tick();tick();tick()
assert(#of('bitmap')==3 and #of('destroy_gui')==3,'bitmaps '..#of('bitmap'))
S.stop()
assert(#W.runtime.writes==0)
""")

    def test_another_build_draws_nothing(self):
        self.check(r"""
panel(0,11,their_cards())
SYNCED[THEM]={[1]='orbital_gas_barrage'}
local pin=TH.pins[1]
local saved=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,string.char((saved:byte()+1)%256))
local S=overlay.mission_remote_slots(source)
tick();tick()
assert(#of('create_screen_gui')==0)
assert(count('TEAMMATE HUD OVERLAY REFUSED: not drawn: game+'..string.format('%X',pin.rva)..' changed (')==1,
    table.concat(logged,' | '))
local world=assert(world_module.open())
local none,why=overlay.teammate_cards(world)
assert(none==nil and why:find('changed',1,true),tostring(why))
S.stop()
""")


if __name__ == '__main__':
    unittest.main()
