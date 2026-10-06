"""Slot-local loadout icons (development; docs/custom-stratagems.md, "Slot-local loadout icons";
runtime/stratagem_slot_icons.lua): a virtual slot's native loadout widget shows a VANILLA icon on the token's atlas page
(Orbital Gas Strike's on an Orbital Precision Strike slot) by guarded data writes to that slot's own icon element (its
sprite rectangle and UV, and the dirty bits the game's image setter sets), re-applied after every repaint, put back when
the slot is no longer virtual. No StratagemInfo write: a native Precision Strike slot keeps its icon. Offline: the event
world with a loadout screen whose slot widgets carry icon elements (the game's image setter and scene update emulated),
the atlas sprite map with both icons on one page, and the selector's virtual slots."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

ICONS = r"""
local icons=require('hd2runtime/runtime/stratagem_slot_icons')
local PAGE='0x5207684C3952B0CC'
local PREC_RECT,GAS_RECT={0.42578125,0.47265625,0.0625,0.0625},{0.49609375,0.4921875,0.0625,0.0625}
-- The rows' icons and colour sets as the research read them: Orbital Precision Strike (type 118) 0x53031033EE7A60E3,
-- Orbital Gas Strike (type 41) 0x78F1E50B852CFB79, both colour set 0, both sprites on atlas page 0x5207684C3952B0CC.
W.write(ROW[118]+0xB0,W.u32(0xEE7A60E3)..W.u32(0x53031033));W.write(ROW[118]+0xB8,W.u32(0))
W.write(ROW[41]+0xB0,W.u32(0x852CFB79)..W.u32(0x78F1E50B));W.write(ROW[41]+0xB8,W.u32(0))
local function atlas(spec)
    spec=spec or{}
    W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT},sprites={
        {hash='0x53031033EE7A60E3',atlasHash=PAGE,rect=PREC_RECT},
        {hash='0x78F1E50B852CFB79',atlasHash=spec.gasPage or PAGE,rect=GAS_RECT}}})
end
-- The virtual definition again, now naming a slot icon: Orbital Gas Strike's (vanilla, borrowed).
virtual.reset_for_tests()
GAS=virtual.define({id='orbital_gas_barrage',display={name=texts.handle('ogb_name2','Orbital Gas Barrage',MOD),
    description=texts.handle('ogb_description2','Calls down a barrage of gas shells.',MOD),icon=ICON,
    slot_icon='Orbital Gas Strike'},selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'}},MOD)
local event_world=require('hd2runtime/runtime/event_world')
selector.watch(function(event,view)if event=='record_changed'then selector.track(event_world.open(),view)end end)
local function same(a,b)for i=1,4 do if math.abs(a[i]-b[i])>1e-6 then return false end end;return true end
"""


def lua(body):
    return run(WORLD + SELECT + ICONS + body)


class SlotIconTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_a_virtual_slot_shows_the_borrowed_icon_and_a_native_slot_of_the_same_token_keeps_its_own(self):
        self.check(r"""
atlas()
-- Slot 0 holds the REAL Orbital Precision Strike; the selector is open on slot 1 (Eagle Airstrike).
SCREEN=W.loadout_screen({entries={{type=118},{type=22}},editedSlot=1})
SCREEN.frame()
assert(same(SCREEN.rect(0),PREC_RECT),'the native slot shows the token icon')
local S=icons.follow()
tick(2)
assert(#W.runtime.writes==0,'no virtual slot: nothing written')
local first=#W.runtime.writes
local job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=selector.advance}))
assert(job.status=='selected'and job.index==1)
tick(3)
-- [Precision icon] [Gas icon]: only slot 1's own element changed.
assert(same(SCREEN.rect(1),GAS_RECT)and same(SCREEN.rect(0),PREC_RECT),table.concat(logged,' | '))
SCREEN.frame()
assert(same(SCREEN.pushes[1],GAS_RECT),'the scene update pushed the borrowed rectangle to the slot primitive')
assert(count("SLOT ICON: slot 1 (virtual orbital_gas_barrage) shows Orbital Gas Strike's icon (vanilla, borrowed: atlas "
    ..'page 0x5207684C3952B0CC')==1,table.concat(logged,' | '))
local I=SEL.slotIcon
local e1=SCREEN.element(1)
local allowed={}
for o=I.rect,I.rect+12,4 do allowed[e1+o]=true end
for o=I.uv,I.uv+12,4 do allowed[e1+o]=true end
allowed[e1+I.flags]=true;allowed[SCREEN.parent(1)+I.flags]=true;allowed[SCREEN.root+I.flags]=true
local icon_writes=0
for _,w in ipairs(writes_from(first))do
    if w.address>=SCREEN.ui+SEL.loadout.panel0Widgets or allowed[w.address]then
        if allowed[w.address]then icon_writes=icon_writes+1 end
    end
end
assert(icon_writes>=6,'rectangle, UV and dirty bits: '..icon_writes)
for k=0,3 do if k~=1 then
    for _,w in ipairs(writes_from(first))do
        assert(not(w.address>=SCREEN.element(k)and w.address<SCREEN.element(k)+0x160),'slot '..k..' icon untouched')
    end
end end
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed (no global presentation)')
-- A second virtual slot: the repaint resets every slot, the follower re-applies both virtual ones.
job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=selector.advance}))
assert(job.status=='selected'and job.index==2)
tick(3)
assert(same(SCREEN.rect(0),PREC_RECT)and same(SCREEN.rect(1),GAS_RECT)and same(SCREEN.rect(2),GAS_RECT))
assert(count('slot 1 icon re-applied after the game repainted the slots')>=1)
-- Undo the newest (slot 2): its icon goes back to the token's with the repaint or by the follower.
assert(settle_job(selector.restore()).status=='restored')
tick(3)
assert(same(SCREEN.rect(1),GAS_RECT)and same(SCREEN.rect(2),PREC_RECT),table.concat(logged,' | '))
-- Off: slot 1 gets its own icon back without a repaint.
S.set_enabled(false)
tick(2)
assert(same(SCREEN.rect(1),PREC_RECT)and count('slot 1 is no longer virtual: its own icon put back')==1)
S.stop()
assert(W.read(settings.base,settings.size)==SETTINGS)
return 'ok'
""")

    def test_replacement_and_mixed_precision_slots_with_the_native_highlight_following(self):
        self.check(r"""
atlas()
local slot_focus=require('hd2runtime/runtime/stratagem_slot_focus')
local FO=SEL.slotFocus
local function u32_at(at)local s=W.read(at,4);return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216 end
-- [native Precision Strike] [Eagle Airstrike] [empty] [empty]; the selector open on slot 1 (the highlight there).
SCREEN=W.loadout_screen({entries={{type=118},{type=22}},editedSlot=1})
SCREEN.frame()
local S=icons.follow()
local job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=slot_focus.advance}))
assert(job.status=='selected'and job.index==1 and job.written and not job.appended,'Eagle Airstrike replaced')
assert(job.advance.status=='advanced'and job.advance.slot==2 and job.advance.verified,tostring(job.advance.reason))
tick(3)
-- The native highlight and the edited slot on slot 2, the next empty slot; the replaced slot holds the token.
assert(u32_at(SCREEN.panel+FO.focus)==2 and u32_at(SCREEN.ui+SEL.loadout.editedSlot)==2)
assert(SCREEN.entry(0)==118 and SCREEN.entry(1)==118 and SCREEN.count()==2)
-- Mixed: slot 0 the native Precision Strike keeps its icon; slot 1 the virtual Gas Barrage shows Gas Strike's.
assert(same(SCREEN.rect(0),PREC_RECT)and same(SCREEN.rect(1),GAS_RECT),table.concat(logged,' | '))
local set=selector.virtual_slots()
assert(set.slots[0]==nil and set.slots[1].definition=='orbital_gas_barrage')
S.stop()
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed (no global presentation)')
return 'ok'
""")

    def test_an_icon_that_cannot_be_shown_by_data_is_refused_with_nothing_written(self):
        self.check(r"""
-- The borrowed icon on another atlas page: binding another texture is an engine call, so nothing is written.
atlas({gasPage='0x6E09D5A15DEC6F79'})
SCREEN=W.loadout_screen({entries={{type=118}},editedSlot=1})
local S=icons.follow()
assert(settle_job(selector.select('orbital_gas_barrage')).status=='selected')
local after=#W.runtime.writes
tick(3)
assert(#W.runtime.writes==after and same(SCREEN.rect(1),PREC_RECT))
assert(count("only an icon on the same page can be shown by data")==1,table.concat(logged,' | '))
S.stop()
-- Another colour set than the token: refused.
selector.reset_for_tests()
atlas()
W.write(ROW[41]+0xB8,W.u32(2))
SCREEN=W.loadout_screen({entries={{type=118}},editedSlot=1})
S=icons.follow()
assert(settle_job(selector.select('orbital_gas_barrage')).status=='selected')
after=#W.runtime.writes
tick(3)
assert(#W.runtime.writes==after and count('has another colour set than the token')==1)
S.stop()
W.write(ROW[41]+0xB8,W.u32(0))
-- The element's rectangle is not the token sprite's (the atlas data changed): refused.
selector.reset_for_tests()
atlas()
SCREEN=W.loadout_screen({entries={{type=118}},editedSlot=1})
S=icons.follow()
assert(settle_job(selector.select('orbital_gas_barrage')).status=='selected')
W.write(SCREEN.element(1)+SEL.slotIcon.rect,W.f32(0.1))
after=#W.runtime.writes
tick(3)
assert(#W.runtime.writes==after and count("rectangle is not the token sprite's")==1,table.concat(logged,' | '))
S.stop()
-- A definition without a slot icon: nothing is ever written to a slot icon.
selector.reset_for_tests()
virtual.reset_for_tests()
virtual.define({id='plain_gas',display={name=texts.handle('pg_name','Plain Gas',MOD),description=texts.handle('pg_d',
    'Plain.',MOD),icon=ICON},selection={token='Orbital Precision Strike'},mission={carrier='Orbital 120mm HE Barrage'}},MOD)
atlas()
SCREEN=W.loadout_screen({entries={{type=118}},editedSlot=1})
S=icons.follow()
assert(settle_job(selector.select('plain_gas')).status=='selected')
after=#W.runtime.writes
tick(3)
assert(#W.runtime.writes==after and same(SCREEN.rect(1),PREC_RECT))
S.stop()
-- The definition: a slot icon must be a catalogued stratagem other than the token.
local ok=pcall(virtual.define,{id='bad',display={name=texts.handle('b1','B',MOD),description=texts.handle('b2','B',MOD),
    icon=ICON,slot_icon='Orbital Precision Strike'},selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'}},MOD)
assert(not ok)
ok=pcall(virtual.define,{id='bad2',display={name=texts.handle('b3','B',MOD),description=texts.handle('b4','B',MOD),
    icon=ICON,slot_icon='No Such Stratagem'},selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'}},MOD)
assert(not ok)
assert(W.read(settings.base,settings.size)==SETTINGS)
return 'ok'
""")

    def test_the_uv_is_computed_as_the_image_setter_computes_it(self):
        self.check(r"""
local uv=icons.uv_for({0,0,1,1},GAS_RECT)
assert(uv[1]==0.49609375 and uv[2]==0.4921875 and uv[3]==0.55859375 and uv[4]==0.5546875)
uv=icons.uv_for({0.25,0.5,0.75,1},{0.1,0.2,0.5,0.25})
local b=require('hd2runtime/core/bytes')
local function r32(v)return b.value(b.encode(v,'f32'),0,'f32')end
assert(uv[1]==r32(r32(0.25*0.5)+0.1)and uv[4]==r32(r32(1*0.25)+0.2),'single precision, multiply then add')
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
