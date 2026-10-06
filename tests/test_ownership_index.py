"""The account catalogue index of stratagem ownership (runtime/stratagem_slot_conversion.lua ownership): a carrier
discovery asks for about a hundred stratagems' ownership; inside a Runtime update the catalogue range is read once (its
index array in one read, each record's id once) and every lookup of that update uses it. The answers equal the
per-stratagem scan's; outside an update the scan runs as before; the next update reads the catalogue again; a record
that no longer holds its id falls back to the scan."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT

INDEX = r"""
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local scheduler=require('hd2runtime/runtime/scheduler')
local CAT=require('hd2runtime/domains/stratagem_slots').catalogue
-- Owned (2, 4), not owned (0), and ids the catalogue does not hold.
local STATES={[1001]=2,[1002]=0,[1003]=4,[1004]=0,[1005]=2}
local cat=W.catalogue(STATES)
local IDS={1001,1002,1003,1004,1005,1006,7777}
local world=assert(world_module.open())
local function answers()
    local out={}
    for _,id in ipairs(IDS)do
        local r=slots.ownership(world,id)
        out[#out+1]=('%d=%s/%s/%s'):format(id,tostring(r.owned),tostring(r.found),tostring(r.state))
    end
    return table.concat(out,' ')
end
-- Counts the reads of the catalogue's index (one per lookup position for the scan; one array read for the index).
local index_reads,array_reads=0,0
local real=world.runtime.read
world.runtime.read=function(at,n)
    if at>=cat+CAT.index and at<cat+CAT.index+4*16 then
        if n==4 then index_reads=index_reads+1 else array_reads=array_reads+1 end
    end
    return real(at,n)
end
-- Runs fn inside one Runtime update.
local function in_update(fn)
    local result
    local w={status='waiting'}
    function w.cancel()w.status='cancelled'end
    function w.tick()result=fn();w.status='complete'end
    scheduler.attach(w)
    update(0.1)
    return result
end
"""


class OwnershipIndexTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + INDEX + body + "\nreturn 'ok'"), b'ok')

    def test_the_index_answers_exactly_as_the_scan_and_reads_the_catalogue_once_per_update(self):
        self.check(r"""
local scanned=answers()
assert(scanned=='1001=true/true/2 1002=false/true/0 1003=true/true/4 1004=false/true/0 1005=true/true/2 '
    ..'1006=false/false/nil 7777=false/false/nil',scanned)
assert(index_reads>7 and array_reads==0,'outside an update: the scan, one index read per position')
index_reads,array_reads=0,0
local indexed=in_update(answers)
assert(indexed==scanned,indexed)
assert(array_reads==1 and index_reads==0,'inside an update: the index array once, no per-position reads '
    ..array_reads..' '..index_reads)
-- The next update reads it again (a purchase between updates is seen).
W.write(cat+CAT.definitions+1*CAT.definitionStride+CAT.definitionState,W.u32(2))
index_reads,array_reads=0,0
local after=in_update(answers)
assert(array_reads==1 and after:find('1002=true/true/2',1,true),after)
""")

    def test_a_record_that_changed_after_the_index_falls_back_to_the_scan(self):
        self.check(r"""
local result=in_update(function()
    local first=slots.ownership(world,1003)
    -- The record that held 1003 now holds another id: its lookup scans again (and no longer finds it).
    W.write(cat+CAT.records+2*CAT.recordStride+CAT.recordId,W.u32(4242))
    index_reads=0
    local again=slots.ownership(world,1003)
    return {first=first,again=again,scan_reads=index_reads}
end)
assert(result.first.found==true and result.first.owned==true)
assert(result.again.found==false and result.scan_reads>0,'the scan decided '..tostring(result.scan_reads))
""")


if __name__ == '__main__':
    unittest.main()
