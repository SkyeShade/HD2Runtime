"""0.30.2 (live report on dev5): carriers go to the custom stratagems a player PICKED first. Registered but unpicked
ones are allocated only tentatively (runtime/carrier_allocator.lua, d.selected == false): each gets the first carrier
no picked custom stratagem and no native pick holds, takes nothing from another unpicked one and reserves nothing. So
with more red-beacon custom stratagems registered than red orbitals owned (the report: four Pelicans and two barrages,
five orbitals), no tile is dimmed until picking it would really leave it without a carrier, and a pick is never refused
because an unpicked definition took its carrier."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD

HARNESS = WORLD + r'''
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local A=require('hd2runtime/runtime/carrier_allocator')
local function cand(name,id)
    return {name=name,id=id,type=id,family='orbital',class=1,beaconCategory='offensive',beamColour='red',
        pingColour='red',eligible=true,reasons={},codes={}}
end
local ALL={cand('Orbital 380mm HE Barrage',1),cand('Orbital Napalm Barrage',2),cand('Orbital Walking Barrage',3),
    cand('Orbital Smoke Strike',4),cand('Orbital Gatling Barrage',5)}
slots.discover_carriers=function(world,token,opts)
    local out={ready=true,candidates={}}
    for _,c in ipairs(ALL)do
        local copy={};for k,v in pairs(c)do copy[k]=v end
        copy.reasons={}
        if opts.present[c.id]then copy.eligible=false;copy.reasons={'in_loadout'};copy.codes={'in_loadout'}end
        out.candidates[#out.candidates+1]=copy
    end
    return out
end
local IDS={'gas_barrage','ems_barrage','pelican_cas','pelican_cannon','pelican_ems','pelican_gas'}
local function defs(picked)
    local out={}
    for _,id in ipairs(IDS)do
        out[#out+1]={id=id,label=id,token='Orbital Precision Strike',selected=picked[id]==true,
            policy={beacon='offensive',prefer_families={'orbital'}}}
    end
    return out
end
local function allocate(picked,present)
    return A.allocate_lobby(world_module.open(),defs(picked),{present=present or{},players=1},{})
end
'''


class PickedFirstTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_nothing_picked_every_tile_is_available_and_nothing_is_reserved(self):
        self.check(r'''
local a=allocate({})
for _,id in ipairs(IDS)do
    assert(a.assignments[id]and a.assignments[id].tentative,id..' is tentative')
    assert(not a.refused[id],id)
end
assert(next(a.reservations)==nil,'an unpicked definition reserves nothing')
''')

    def test_picks_take_carriers_first_and_only_a_really_full_group_dims_a_tile(self):
        self.check(r'''
-- Gas Barrage picked: it takes a carrier; the five others share the four left, tentatively, all still available.
local a=allocate({gas_barrage=true})
assert(not a.assignments.gas_barrage.tentative)
local gas=a.assignments.gas_barrage.stable_id
assert(a.reservations[gas]=='gas_barrage')
for _,id in ipairs(IDS)do
    if id~='gas_barrage'then
        local x=a.assignments[id]
        assert(x and x.tentative and x.stable_id~=gas,id)
    end
end
-- Four picked and one orbital in the native loadout: the four take four, nothing is left for the other two.
local b=allocate({gas_barrage=true,pelican_cas=true,pelican_cannon=true,pelican_ems=true},{[5]=true})
for _,id in ipairs({'gas_barrage','pelican_cas','pelican_cannon','pelican_ems'})do
    assert(b.assignments[id]and not b.assignments[id].tentative,id..' keeps a carrier')
end
assert(b.refused.ems_barrage and b.refused.pelican_gas,'the full group dims the unpicked tiles')
-- Three picked, one native: one orbital is free, so both unpicked tiles stay available (either may be picked).
local c=allocate({gas_barrage=true,pelican_cas=true,pelican_cannon=true},{[5]=true})
assert(c.assignments.ems_barrage.tentative and c.assignments.pelican_gas.tentative)
assert(c.assignments.ems_barrage.stable_id==c.assignments.pelican_gas.stable_id,'they may share a tentative carrier')
local n=0
for _ in pairs(c.reservations)do n=n+1 end
assert(n==3,'only the picks reserve: '..n)
assert(c.distinct,'the picks never share')
''')

    def test_a_pick_is_never_refused_because_an_unpicked_definition_ranked_first(self):
        self.check(r'''
-- pelican_gas sorts last by id, and every definition has the same five candidates: before 0.30.2 the first five ids
-- took them and the picked pelican_gas was refused. Now the pick goes first.
local a=allocate({pelican_gas=true})
assert(a.assignments.pelican_gas and not a.assignments.pelican_gas.tentative)
assert(not a.refused.pelican_gas)
''')


if __name__ == '__main__':
    unittest.main()
