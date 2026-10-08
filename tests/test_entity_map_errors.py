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
