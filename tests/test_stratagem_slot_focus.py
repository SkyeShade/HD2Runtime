"""The native loadout slot highlight (development; docs/custom-stratagems.md, "Moving the native slot highlight";
runtime/stratagem_slot_focus.lua; research slotFocus): the local panel's focus and previous focus, bit 1 on the old and
new slot widgets and the frame-flash byte on both, in one guarded transaction; the game's own panel update then
consumes the bytes and redraws both widgets from their flags (0x1894C30..0x1894C57). Offline: the event world with a
loadout screen whose local panel carries the focus fields, the widget flags and frames, with the panel update's flash
handling and the widget visual update emulated."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

FOCUS = r"""
local focus=require('hd2runtime/runtime/stratagem_slot_focus')
local FO=SEL.slotFocus
local function u32_at(at)local s=W.read(at,4);return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216 end
local function widget(k)return SCREEN.ui+SEL.loadout.panel0Widgets+k*SEL.loadout.widgetStride end
local function f32_at(at)return require('hd2runtime/core/bytes').value(W.read(at,4),0,'f32')end
local function focused(k)return math.floor(SCREEN.widget_flags(k)/FO.focusedBit)%2==1 end
-- Every address the move may write: the focus pair, each widget's flags byte and flash byte, the edited slot.
local function allowed(with_edited)
    local out={[SCREEN.panel+FO.focus]=true,[SCREEN.panel+FO.previous]=true}
    for k=0,3 do out[widget(k)+FO.widgetFlags]=true;out[widget(k)+FO.flash]=true end
    if with_edited then out[SCREEN.ui+SEL.loadout.editedSlot]=true end
    return out
end
"""


def lua(body):
    return run(WORLD + SELECT + FOCUS + body)


class SlotFocusTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_highlight_moves_0_1_2_3_and_nothing_else_changes(self):
        self.check(r"""
-- The native selector open on slot 0 (the focus on slot 0, the selection-open bit on every widget).
SCREEN=W.loadout_screen({entries={{type=136},{type=22}},editedSlot=0})
SCREEN.frame()
assert(focused(0)and not focused(1)and u32_at(SCREEN.panel+FO.focus)==0)
local record=W.read(SCREEN.record+0x188,0x788+4-0x188)
local edited=u32_at(SCREEN.ui+SEL.loadout.editedSlot)
local types={};for k=0,3 do types[k]=SCREEN.widget(k)end
for to=1,3 do
    local first=#W.runtime.writes
    local job=settle_job(focus.move(to))
    assert(job.status=='moved'and job.from==to-1 and job.to==to and job.all and job.others,
        tostring(job.status)..' '..tostring(job.code)..' '..tostring(job.reason)..' '..table.concat(logged,' | '))
    -- The focus pair, the flags, and the game's own redraw (the bytes consumed, both frames as 0x18932F0 draws them).
    assert(u32_at(SCREEN.panel+FO.focus)==to and u32_at(SCREEN.panel+FO.previous)==to-1)
    assert(focused(to)and not focused(to-1))
    assert(W.read(widget(to)+FO.flash,1):byte()==0 and W.read(widget(to-1)+FO.flash,1):byte()==0,'consumed')
    assert(f32_at(widget(to)+FO.thickness)==3 and f32_at(widget(to)+FO.gap)==0 and f32_at(widget(to-1)+FO.gap)==16)
    assert(f32_at(widget(to)+FO.frame+FO.opacity)==0 and f32_at(widget(to)+FO.selectedElement+FO.opacity)==1)
    local ok_addresses=allowed(false)
    local wrote=0
    for k=first+1,#W.runtime.writes do
        local w=W.runtime.writes[k]
        assert(ok_addresses[w.address],string.format('a write outside the highlight: %X',w.address))
        wrote=wrote+1
    end
    assert(wrote==6,'focus, previous, two flags, two flash bytes: '..wrote)
end
-- Nothing else: the record, the edited slot (still 0: the next pick still lands in slot 0), the selection, the types.
assert(W.read(SCREEN.record+0x188,0x788+4-0x188)==record and u32_at(SCREEN.ui+SEL.loadout.editedSlot)==edited)
assert(W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()==1)
for k=0,3 do assert(SCREEN.widget(k)==types[k])end
assert(count('slot focus MOVED: the native highlight went from slot 2 to slot 3')==1,table.concat(logged,' | '))
assert(count('every other loadout field unchanged (record, edited slot, selection, slot types, cached record pointer): '
    ..'true')==3)
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed')
return 'ok'
""")

    def test_with_the_edited_slot_the_next_pick_lands_on_the_highlighted_slot(self):
        self.check(r"""
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=1})
SCREEN.frame()
local job=settle_job(focus.move(2,nil,{edited=true}))
assert(job.status=='moved'and job.edited and job.verified.edited and job.others,tostring(job.code)..' '..tostring(job.reason))
assert(u32_at(SCREEN.ui+SEL.loadout.editedSlot)==2 and focused(2)and not focused(1))
-- The edited slot moves only while a selection is open.
SCREEN.set('selecting',false)
SCREEN.frame()
local refused=settle_job(focus.move(3,nil,{edited=true}))
assert(refused.status=='refused'and refused.code=='NO_SELECTION')
-- Without the selection open the highlight still moves (the frames drawn without the selection state).
job=settle_job(focus.move(3))
assert(job.status=='moved'and f32_at(widget(3)+FO.frame+FO.opacity)==1 and f32_at(widget(3)+FO.thickness)==3)
return 'ok'
""")

    def test_every_refusal_writes_nothing_and_unconsumed_bytes_are_put_back(self):
        self.check(r"""
local function refused(code,setup,target,opts)
    SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
    SCREEN.frame()
    if setup then setup()end
    local first=#W.runtime.writes
    local job=settle_job(focus.move(target or 1,nil,opts))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..' '..tostring(job.reason))
    assert(#W.runtime.writes==first,code..' wrote')
end
refused('SAME_SLOT',nil,0)
refused('BAD_SLOT',nil,4)
refused('DISABLED',function()W.write(widget(1)+FO.widgetFlags,string.char(FO.selectionBit+FO.disabledBit))end)
refused('FLASH_PENDING',function()W.write(widget(1)+FO.flash,string.char(1))end)
refused('TWEEN',function()
    W.write(widget(0)+FO.frame,W.u32(FO.colourTweenFlag));W.write(widget(0)+FO.frame+FO.colourTween,W.u32(5))
end)
refused('PANEL_MODE',function()W.write(SCREEN.ui+SEL.loadout.panelMode,W.u32(1))end)
refused('NOT_LOCAL_GROUP',function()W.write(SCREEN.ui+FO.activeGroup,W.u32(1))end)
refused('UNBOUND',function()W.write(SCREEN.ui+FO.containerBound,W.u64(0))end)
refused('REPAINT_PENDING',function()W.write(SCREEN.ui+SEL.loadout.panel0BoundRecord,W.u64(0))end)
refused('STATE',function()W.write(widget(0)+FO.widgetFlags,string.char(FO.selectionBit))end)
refused('READY',function()SCREEN.set('ready',true)end)
refused('SCREEN_CLOSED',function()SCREEN.close()end)
-- The panel update does not run (no consumption within a second): everything written is put back.
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
SCREEN.frame()
SCREEN.panelUpdate=false
local job=settle_job(focus.move(1))
assert(job.status=='reverted'and job.undo and job.undo.status=='APPLIED',tostring(job.status))
assert(u32_at(SCREEN.panel+FO.focus)==0 and focused(0)and not focused(1))
assert(W.read(widget(0)+FO.flash,1):byte()==0 and W.read(widget(1)+FO.flash,1):byte()==0)
assert(count('slot focus NOT CONSUMED')==1)
assert(W.read(settings.base,settings.size)==SETTINGS)
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
