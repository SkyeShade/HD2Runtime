"""The Ongoing probe (2026-10-07; runtime/ongoing_probe.lua): READ-ONLY. A new call of one of this player's record
entries is followed (one line a second and one at every HUD state change) until a few seconds after its HUD slot shows
the cooldown, with the entry's times and unknown 8 bytes, the HUD slot's floats and the call's beacons; nothing is ever
written. Offline: the slot cooldown world (the 380mm carrier converted from the virtual Gas Barrage slot)."""
import unittest

from support import run
from test_slot_cooldown import lua as cool_lua

PROBE = r"""
local probe=require('hd2runtime/runtime/ongoing_probe');probe.reset_for_tests()
local world_module=require('hd2runtime/runtime/event_world')
local function steps(n,dt)for _=1,n do probe.step(world_module.open(),dt or 0.5)end end
local function hud_state(h,state)
    local slot=h.slots[INDEX].address
    local bar=slot+CD.hud.bar
    W.write(bar+CD.hud.barIndex,W.u32(INDEX));W.write(bar+CD.hud.barState,W.u32(state))
end
"""


class OngoingProbeTests(unittest.TestCase):
    def test_a_call_is_followed_read_only_until_after_its_cooldown_shows(self):
        self.assertEqual(cool_lua(PROBE + r'''
local h=converted()
local writes=#W.runtime.writes
steps(2)
assert(count('ONGOING PROBE')==0,'nothing before a call')
-- The game's call (activated now, arriving 6 s later); the HUD inbound.
local arrival=call(h,CLOCK,6,205.2)
W.write(entry_at(h)+0x28,W.u32(0x12345678)..W.u32(7))
hud_state(h,CD.hud.inbound)
steps(1)
assert(count('ONGOING PROBE entry '..INDEX..' (type 125): a NEW CALL: its row: cooldown 240.00 s')==1,
    table.concat(logged,' | '))
assert(count('[HUD state nil -> 3]')==1 and count('+0x28 78563412')==1 and count('u32 305419896 7')==1,
    table.concat(logged,' | '))
assert(count('+0x3714 ')>=1 and count('+0x371C ')>=1 and count('+0x3724 ')>=1,'the HUD floats')
-- One line a second while it runs.
steps(4)
local n=count('ONGOING PROBE entry '..INDEX..' (type 125) t ')
assert(n>=2 and n<=4,n)
-- The cooldown shows: a line at the change, then the end 5 s later.
hud_state(h,CD.hud.cooling)
steps(1)
assert(count('[HUD state 3 -> 4]')==1,table.concat(logged,' | '))
steps(12)
assert(count('ONGOING PROBE entry '..INDEX..' (type 125): END after ')==1 and count('(its cooldown showed)')==1,
    table.concat(logged,' | '))
local after=count('ONGOING PROBE')
steps(6)
assert(count('ONGOING PROBE')==after,'nothing after the end')
assert(#W.runtime.writes==writes,'the probe wrote')
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
