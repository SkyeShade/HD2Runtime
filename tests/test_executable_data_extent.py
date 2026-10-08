"""Reviewed data in executable pages (2026-10-08, the user's decision; core/page_protection.lua register_executable_data,
core/guarded_transaction.lua): game.dll keeps the armor weight-class tables and the avatar damage curve in pages the
loader maps PAGE_EXECUTE_READWRITE. Such a page is a write target only for exact extents a domain registered after
its own proofs, and only when every change of the transaction on that page lies inside one; it is never re-protected.
Every other executable page, and every unregistered byte of a registered page, stays refused before anything is
written."""
import unittest

from support import run
from test_proton_page_protection import MEMORY

EXEC = MEMORY.replace(
    "assert(page_protect(at-at%PAGE)==protection.READWRITE,'write without a writable page')",
    "local p=page_protect(at-at%PAGE)\n"
    " assert(p==protection.READWRITE or p==protection.EXECUTE_READWRITE,'write without a writable page')") + r'''
protection.reset_executable_data_for_tests()
-- An executable-data page of the image: the class table at +0x3000 (three f32), as the loader maps it (0x40).
local TABLE=IMAGE+0x3000
protect[TABLE-TABLE%PAGE]=protection.EXECUTE_READWRITE
poke(TABLE,u32(0)..u32(0x3F800000)..u32(0x40000000))
local exec={base=IMAGE,size=IMAGE_SIZE,type=0x1000000,protect=protection.EXECUTE_READWRITE}
local function table_plan(offsets)
 local changes={}
 for _,o in ipairs(offsets)do
  local current=runtime.read(TABLE+o,4)
  changes[#changes+1]={label='armor_class.rating',owner=exec,offset=0x3000+o,expected=current,desired=u32(0x3F000000),
   before=current}
 end
 return {changes=changes,snapshots={{owner=exec,offset=0x3000,bytes=runtime.read(TABLE,12)}}}
end
'''


def check(body):
    return run(EXEC + body + "\nreturn 'ok'")


class ExecutableDataTests(unittest.TestCase):
    def test_an_unregistered_executable_page_is_refused_before_anything_is_written(self):
        self.assertEqual(check(r'''
local report=guarded.apply(runtime,table_plan({8}))
assert(report.status=='REJECTED'and calls.write==0 and calls.protect==0,tostring(report.status)..' '..tostring(report.reason))
assert(runtime.read(TABLE+8,4)==u32(0x40000000))
'''), b'ok')

    def test_a_registered_extent_is_written_without_any_protection_change(self):
        self.assertEqual(check(r'''
protection.register_executable_data(TABLE+8,4,'heavy armor value')
local report=guarded.apply(runtime,table_plan({8}))
assert(report.status=='APPLIED',tostring(report.status)..' '..tostring(report.reason))
assert(calls.protect==0 and report.protection_changes==0 and report.protection_restored==true)
assert(runtime.read(TABLE+8,4)==u32(0x3F000000)and runtime.read(TABLE,4)==u32(0)
    and runtime.read(TABLE+4,4)==u32(0x3F800000),'only the registered entry changed')
assert(page_protect(TABLE-TABLE%PAGE)==protection.EXECUTE_READWRITE)
'''), b'ok')

    def test_a_change_outside_the_registered_extent_on_the_same_page_refuses_the_whole_page(self):
        self.assertEqual(check(r'''
protection.register_executable_data(TABLE+8,4,'heavy armor value')
local report=guarded.apply(runtime,table_plan({4,8}))
assert(report.status=='REJECTED'and calls.write==0,tostring(report.status))
assert(runtime.read(TABLE+4,4)==u32(0x3F800000)and runtime.read(TABLE+8,4)==u32(0x40000000))
'''), b'ok')

    def test_registration_is_exact_and_bounded(self):
        self.assertEqual(check(r'''
protection.register_executable_data(TABLE+8,4,'a')
protection.register_executable_data(TABLE+8,4,'a')                     -- the same extent again: kept once
assert(protection.reviewed_executable_data(TABLE+8,4)=='a'and protection.reviewed_executable_data(TABLE+8,8)==nil
    and protection.reviewed_executable_data(TABLE+4,4)==nil)
assert(not pcall(protection.register_executable_data,TABLE+10,4,'overlap'))
assert(not pcall(protection.register_executable_data,TABLE,65,'too large'))
-- Copy-on-write and executable-read pages are never writable, registered or not.
assert(not protection.writable_target(protection.EXECUTE_READWRITE)and not protection.writable_target(protection.WRITECOPY))
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
