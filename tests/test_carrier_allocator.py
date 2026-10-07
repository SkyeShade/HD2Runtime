"""Carrier allocation for several custom stratagems (runtime/carrier_allocator.lua; research/docs/pelican-cas-
F5FEE03DCFDB.md, "Carrier allocation"): the Gas Barrage takes its own discovery's carrier and reserves its
payload-compatible family; the Pelican CAS takes another RED-beacon carrier (the beam colour, row +0xD4; never the
delivery family): an orbital, then an Eagle, then any other red carrier; a definition with nothing left is refused (its
explicit fallback), never given a shared carrier; nothing is written. Offline: the payload world (the 380mm is the only
payload-compatible carrier, the Airburst Strike a plain orbital; the rows carry their observed beams and pings)."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD

ALLOCATOR = r"""
local allocator=require('hd2runtime/runtime/carrier_allocator')
local present={[PRECISION_ID]=true,[ID22]=true,[ID130]=true}
local function allocate(extra)
    local set={}
    for k,v in pairs(present)do set[k]=v end
    for k,v in pairs(extra or{})do set[k]=v end
    return allocator.allocate(world_module.open(),allocator.DEFINITIONS,set)
end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + ALLOCATOR + body)


class CarrierAllocatorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_two_custom_stratagems_get_distinct_carriers(self):
        self.check(r'''
pworld()
local writes=#W.runtime.writes
local a=allocate()
assert(a.ready and a.distinct)
assert(a.assignments.orbital_gas_barrage.carrier=='Orbital 380mm HE Barrage')
assert(a.assignments.pelican_close_air_support.carrier=='Orbital Airburst Strike')
assert(a.line=='CUSTOM CARRIER: Gas Barrage = Orbital 380mm HE Barrage (orbital, red beacon), Pelican CAS = Orbital '
    ..'Airburst Strike (orbital, red beacon); distinct = true',a.line)
local p=a.assignments.pelican_close_air_support
assert(p.family=='orbital'and p.beacon=='offensive'and p.beam=='red'and p.ping=='red'and p.tier==1 and not p.fallback)
-- Every candidate carries its family and its beacon category apart.
for _,c in ipairs(a.candidates.pelican_close_air_support)do
    if c.name=='Orbital Airburst Strike'then assert(c.beam==1 and c.beaconCategory=='offensive'and c.ping==0)end
    if c.name=='FX-12 Shield Generator Relay'then assert(c.beaconCategory=='support'and c.beamColour=='blue')end
end
assert(a.verdicts.pelican_close_air_support[ID380]=='red, but taken by Gas Barrage',
    tostring(a.verdicts.pelican_close_air_support[ID380]))
assert(#W.runtime.writes==writes)                                   -- read-only
-- The same account and loadout give the same answer.
assert(allocate().line==a.line)
return 'ok'
''')

    def test_the_gas_barrage_family_is_reserved_and_refusals_never_share(self):
        self.check(r'''
pworld()
-- The Airburst in the loadout: the Pelican CAS has nothing left; it never takes the Gas Barrage's 380mm.
local a=allocate({[AIRBURST_ID]=true})
assert(a.assignments.orbital_gas_barrage.carrier=='Orbital 380mm HE Barrage')
assert(a.assignments.pelican_close_air_support==nil)
assert(a.refused.pelican_close_air_support:find('no unused red (offensive) carrier: 1 red eligible, 1 taken or reserved '
    ..'by an earlier custom stratagem',1,true)and a.refused.pelican_close_air_support:find('fallback: refuse',1,true),
    a.refused.pelican_close_air_support)
assert(a.line:find('Pelican CAS = REFUSED (no unused red (offensive) carrier',1,true),a.line)
-- The 380mm in the loadout: the Gas Barrage is refused; the Pelican CAS still gets the Airburst.
local c=allocate({[ID380]=true})
assert(c.assignments.orbital_gas_barrage==nil and c.refused.orbital_gas_barrage)
assert(c.assignments.pelican_close_air_support.carrier=='Orbital Airburst Strike')
-- A definition given explicitly (not the module's list) follows the same rules: the Airburst when it is free, refused
-- when the only orbital left is the Gas Barrage's reserved 380mm.
local only={id='pelican_close_air_support',label='Pelican CAS',token='Orbital Precision Strike',
    exclude={'Orbital 120mm HE Barrage','Orbital Gas Strike'},beacon='offensive',tiers={{family='orbital'}},
    fallback='refuse'}
local d=allocator.allocate(world_module.open(),{allocator.GAS_BARRAGE,only},present)
assert(d.assignments.pelican_close_air_support.carrier=='Orbital Airburst Strike')
local e=allocator.allocate(world_module.open(),{allocator.GAS_BARRAGE,only},{[PRECISION_ID]=true,[AIRBURST_ID]=true})
assert(e.refused.pelican_close_air_support:find('1 taken or reserved by an earlier custom stratagem',1,true),
    e.refused.pelican_close_air_support)
return 'ok'
''')

    def test_a_blue_orbital_is_never_an_offensive_carrier_unless_the_fallback_says_so(self):
        self.check(r'''
pworld()
-- The Airburst given a BLUE beam (+0xD4 = 2), as the Orbital EMS Strike has: still an orbital, no longer offensive.
W.write(ROW[83]+0xD4,W.u32(2))
local a=allocate()
assert(a.assignments.pelican_close_air_support==nil,'a blue orbital was taken')
assert(a.verdicts.pelican_close_air_support[AIRBURST_ID]=='not offensive: a support beacon (blue beam, red ping)',
    tostring(a.verdicts.pelican_close_air_support[AIRBURST_ID]))
assert(a.refused.pelican_close_air_support:find('fallback: refuse',1,true))
-- An explicit fallback takes it, marked.
local fb={}
for k,v in pairs(allocator.PELICAN_CAS)do fb[k]=v end
fb.fallback={beacon='any'}
local b=allocator.allocate(world_module.open(),{allocator.GAS_BARRAGE,fb},present)
local p=b.assignments.pelican_close_air_support
assert(p and p.carrier=='Orbital Airburst Strike'and p.fallback==true and p.beacon=='support')
assert(b.verdicts.pelican_close_air_support[AIRBURST_ID]=='SELECTED (FALLBACK: not a red beacon)')
-- A red carrier of another family (tier 3) is taken before any fallback: the Airburst red again but in the loadout,
-- and a red non-orbital owned: the FX-12 given a red beam, out of the loadout.
W.write(ROW[83]+0xD4,W.u32(1))
W.write(ROW[22]+0xD4,W.u32(1));W.write(ROW[22]+0x50,W.u32(4294967295));W.write(ROW[22]+0x80,W.u32(2))
W.write(ROW[22]+0xC0,W.u32(1))
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[ID380]=2,[AIRBURST_ID]=2,[ID22]=2})
local c=allocator.allocate(world_module.open(),allocator.DEFINITIONS,{[PRECISION_ID]=true,[ID130]=true,[AIRBURST_ID]=true})
local q=c.assignments.pelican_close_air_support
assert(q and q.carrier=='FX-12 Shield Generator Relay'and q.tier==3 and q.beacon=='offensive'and not q.fallback,
    c.line..' '..tostring(c.refused.pelican_close_air_support))
return 'ok'
''')

    def test_not_ready_until_the_catalogue_shows_the_token(self):
        self.check(r'''
pworld()
W.catalogue({[BIG_ID]=2,[ID380]=2,[AIRBURST_ID]=2})                 -- the token not owned (not filled yet)
local a=allocate()
assert(not a.ready and a.reason:find('Gas Barrage: ',1,true),tostring(a.reason))
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
