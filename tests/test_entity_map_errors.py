"""0.30.2 diagnostics from the stats-editor wish list:
  * R7: an entity map row whose membership list is outside the map body refuses the capture with a message naming the
    row, its resource and its member count (no address); a valid row reads as before (core/bytes.lua membership,
    used by core/entity_catalog.lua and core/entity.lua);
  * R9: the shared-records index says once what its first build cost (core/shared_records.lua build_seconds, one
    log line, the shared_records.build_ms metric)."""
import unittest

from support import ROOT, run


class EntityMapErrorTests(unittest.TestCase):
    def test_a_stray_membership_pointer_names_its_row_and_resource(self):
        self.assertEqual(run(r"""
local b=require('hd2runtime/core/bytes')
-- a relative offset inside the body, and the same as a relocated pointer: both read as the offset
assert(b.membership(400,0x10000,8,4000,320,3,'0xAAAA',4)==400)
assert(b.membership(0x10000+400,0x10000,8,4000,320,3,'0xAAAA',4)==400)
-- outside the body: refused, naming the row, the resource and the count, with no address
local ok,why=pcall(b.membership,0x7FF000123456,0x10000,8,4000,320,17,'0x52E4334E6A128CAF',6)
assert(not ok and why:find('^invalid/ambiguous bounded pointer: entity map row 17 %(resource 0x52E4334E6A128CAF, 6 '
    ..'members%)'),why)
assert(not why:find('7FF000123456',1,true)and not why:find(tostring(0x7FF000123456),1,true),'no address')
return 'ok'
"""), b'ok')

    def test_both_entity_readers_use_the_naming_check(self):
        for name in ('entity_catalog.lua', 'entity.lua'):
            source = (ROOT / 'core' / name).read_text(encoding='utf-8')
            self.assertIn('b.membership(', source, name)
            self.assertNotIn('b.relative(', source, name)


    def test_a_stray_row_refuses_only_its_own_resource(self):
        # 0.30.3 (the 0.30.2 live report: the LAS-12 Sai's row outside the map body refused every typed write). A
        # stray row is a diagnostic of its own resource; every other resource resolves as before; logged once.
        self.assertEqual(run(r"""
local catalog=require('hd2runtime/core/entity_catalog')
-- This hand-built map has no game.dll: the table pointers read as in place (tests/test_component_tables.py covers them).
package.loaded['hd2runtime/core/component_tables']={check=function()return{}end}
local logged={}
require('hd2runtime/runtime/log').emit=function(t)logged[#logged+1]=t end
local function le(n,w)local t={};for i=1,w do t[i]=string.char(n%256);n=math.floor(n/256)end;return table.concat(t)end
local function hex(s)return(s:gsub('.',function(c)return string.format('%02X',c:byte())end))end
local R0,R1=le(0x1111,4)..le(0x2222,4),le(0x3333,4)..le(0x4444,4)
-- The map: a 28-byte header (its body size at +16), two 32-byte rows, row 0's one-member list at body offset 64.
local header=string.rep('\0',16)..le(66,4)..string.rep('\0',8)
local rows=R0..le(64,8)..le(1,8)..string.rep('\0',8)
    ..R1..le(0x7FF000000,8)..le(1,8)..string.rep('\0',8)
local map=header..rows..le(7,2)
-- One component (index 7): its header (the record extent at +16 of it), two index rows, two records.
local cheader=string.rep('\0',16)..le(64,4)..string.rep('\0',8)
local component=le(7,4)..cheader..R0..le(0,4)..le(0,4)..R1..le(1,4)..le(0,4)..string.rep('\0',8)
local OFFSET=4096
local owner={base=0x10000,size=8192}
local reader={read=function(_,at,n)
    local buffer=map..string.rep('\0',OFFSET-4-#map)..component
    return buffer:sub(at+1,at+n)
end}
local profile={map_header=hex(header),map_rows=2,components={X={offset=OFFSET,index=7,header=hex(cheader),
    record_offset=32,records=2,stride=4,indices=2,type=0x12345678}}}
local c=catalog.capture(reader,owner,profile,{'X'})
local good,bad
for _,cand in ipairs(c.candidates)do
    if cand.resourceHash==string.format('0x%016X',0x0000222200001111)then good=cand end
    if cand.resourceHash==string.format('0x%016X',0x0000444400003333)then bad=cand end
end
assert(good and good.entityRow==0 and#good.diagnostics==0,'the good row resolves')
assert(bad and bad.entityRow==nil and bad.diagnostics[1]:find('entity map row 1',1,true),tostring(bad and bad.diagnostics[1]))
assert(#c.strays==1 and c.strays[1].row==1)
assert(c.record(good,'X').index==0,'records of the good row read')
local n=0
for _,l in ipairs(logged)do if l:find('entity map row 1 (resource',1,true)then n=n+1 end end
catalog.capture(reader,owner,profile,{'X'})
local m=0
for _,l in ipairs(logged)do if l:find('entity map row 1 (resource',1,true)then m=m+1 end end
assert(n==1 and m==1,'logged once: '..n..' '..m)
return 'ok'
"""), b'ok')

class SharedRecordsTimingTests(unittest.TestCase):
    def test_the_first_build_is_timed_and_logged_once(self):
        self.assertEqual(run(r"""
local logged={}
require('hd2runtime/runtime/log').emit=function(t)logged[#logged+1]=t end
local S=require('hd2runtime/core/shared_records')
S.reset_index()
S.unlisted_sharing()
S.unlisted_sharing()
local n=0
for _,l in ipairs(logged)do if l:find('shared records index built in',1,true)then n=n+1 end end
assert(n==1 and type(S.build_seconds)=='number'and S.build_seconds>=0,n)
return 'ok'
"""), b'ok')


if __name__ == '__main__':
    unittest.main()
