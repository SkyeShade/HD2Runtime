"""The native-slot texture probe (development, READ ONLY; docs/custom-stratagems.md, "A custom texture in a native slot";
runtime/stratagem_slot_texture_probe.lua; research slotTexture): from a loadout slot's icon element to the render-side
copy of its material and the texture handle every draw reads, each link checked. Offline: the event world with a
loadout screen and, for slot 1, a material instance, its world interface, render interface, render world, the render
world's index and object tables and the render-side material, laid out as the research read them."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT

PROBE = r"""
local probe=require('hd2runtime/runtime/stratagem_slot_texture_probe')
local T,I=SEL.slotTexture,SEL.slotIcon
local event_world=require('hd2runtime/runtime/event_world')
local function q(n)return W.u32(n%4294967296)..W.u32(math.floor(n/4294967296))end
-- Builds slot `slot`'s render chain; returns its parts.
local function chain(slot,opts)
    opts=opts or{}
    local E=SCREEN.element(slot)
    local M,WRI,RI,RW=W.alloc(0x100),W.alloc(0x100),W.alloc(0x100),W.alloc(0x400)
    local index,objects,R=W.alloc(0x100),W.alloc(0x100),W.alloc(0x100)
    local props,handles=W.alloc(0x40),W.alloc(0x40)
    local handle,mask,idx=0x10023,0x7FFF,5
    W.write(E+I.flags,W.u32(I.imageKind*2^I.kindShift+T.elementOwns))
    W.write(E+I.material,q(M))
    W.write(M+T.materialHandle,W.u32(handle));W.write(M+T.materialWorld,q(WRI+T.worldOffset))
    W.write(M+T.materialShader,W.u32(0x3461FF0D));W.write(M+T.materialTemplate,q(0xC0F37978))
    W.write(WRI+T.wriRenderInterface,q(RI));W.write(WRI+T.wriMask,W.u32(mask))
    W.write(RI+T.riRenderWorld,q(RW+T.worldOffset))
    W.write(RW,q(W.EXE+(opts.rwVtable or T.rwVtable)));W.write(RW+T.rwWri,q(WRI))
    W.write(RW+T.rwIndex,q(index));W.write(RW+T.rwObjects,q(objects))
    W.write(index+4*(handle%(mask+1)),W.u32(idx));W.write(objects+8*idx,q(R))
    W.write(R,q(W.EXE+(opts.rmVtable or T.rmVtable)));W.write(R+T.rmKind,W.u32(opts.kind or T.rmKindMaterial))
    W.write(R+T.rmPropCount,W.u32(2));W.write(R+T.rmProps,q(props))
    W.write(props,W.u32(0x1234)..W.u32(opts.property or T.imageProperty))
    W.write(R+T.rmHandleCount,W.u32(2));W.write(R+T.rmHandles,q(handles))
    W.write(handles,W.u32(0x55)..W.u32(0x9CA))
    W.write(R+T.rmShader,W.u32(0x3461FF0D));W.write(R+T.rmTemplate,q(opts.template or 0xC0F37978))
    return {E=E,M=M,R=R}
end
"""


def lua(body):
    return run(WORLD + SELECT + PROBE + body)


class SlotTextureProbeTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_chain_resolves_to_the_handle_every_draw_reads_and_nothing_is_written(self):
        self.check(r"""
SCREEN=W.loadout_screen({entries={{type=118},{type=22}},editedSlot=1})
local c=chain(1)
local world=event_world.open()
local view=selector.screen(world)
local s=probe.slot(world,view,1)
assert(s.valid and s.owns and not s.external and s.r==c.R and s.k==1 and s.texture==0x9CA,tostring(s.why))
-- Slot 0's element has no real material in this fixture: not resolved, said so.
local s0=probe.slot(world,view,0)
assert(not s0.valid and s0.why=='the material is unreadable',tostring(s0.why))
local lines=probe.run(ICON)
local text=table.concat(lines,' | ')
assert(text:find('slot 1 (type 22):',1,true)and text:find('valid; image property at 1, texture handle 0x9CA',1,true),text)
assert(lines[#lines]=='read only: nothing was written'and#W.runtime.writes==0)
return 'ok'
""")

    def test_every_link_is_checked(self):
        self.check(r"""
SCREEN=W.loadout_screen({entries={{type=118},{type=22}},editedSlot=1})
local world=event_world.open()
local function why(opts)chain(1,opts);return probe.slot(world,selector.screen(world),1).why end
assert(why({rwVtable=0x1234})=='the render world vtable differs')
assert(why({rmVtable=0x1234})=='the render object vtable differs')
assert(why({kind=3})=='the render object is not a material')
assert(why({template=0x99})=='the render material template differs')
assert(why({property=0x1111})=='no image property in the render material')
assert(why({})==nil)
assert(#W.runtime.writes==0)
-- No loadout screen: nothing read further.
SCREEN.close()
assert(probe.run(ICON)[1]=='the loadout screen is not open')
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
