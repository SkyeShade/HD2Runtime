"""Data in executable pages (core/page_protection.lua, core/guarded_transaction.lua): game.dll keeps the armor
weight-class tables and the avatar damage curve in pages the loader maps PAGE_EXECUTE_READWRITE. From 2026-10-08 to
0.40.0 a domain could register an exact extent there as reviewed executable data. Since 0.40.1 (the user's decision of
2026-10-19: GameGuard was reported to close the game after armor class writes) every registration is refused, so no
change on an executable page is ever written, and nothing is written or re-protected before the refusal."""
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

    def test_registration_is_refused_and_nothing_is_registered(self):
        self.assertEqual(check(r'''
local ok,why=pcall(protection.register_executable_data,TABLE+8,4,'heavy armor value')
assert(not ok and tostring(why):find('GAME_DLL_EXECUTABLE_DATA: heavy armor value: ',1,true)==1,tostring(why))
assert(tostring(why):find('GameGuard',1,true),'the reason names GameGuard')
assert(protection.reviewed_executable_data(TABLE+8,4)==nil)
-- Arguments are still checked first.
assert(not pcall(protection.register_executable_data,TABLE,65,'too large'))
-- Copy-on-write and executable pages are never writable targets.
assert(not protection.writable_target(protection.EXECUTE_READWRITE)and not protection.writable_target(protection.WRITECOPY))
'''), b'ok')

    def test_a_change_on_an_executable_page_is_refused_after_a_failed_registration(self):
        self.assertEqual(check(r'''
pcall(protection.register_executable_data,TABLE+8,4,'heavy armor value')
local report=guarded.apply(runtime,table_plan({8}))
assert(report.status=='REJECTED'and calls.write==0 and calls.protect==0,tostring(report.status))
assert(runtime.read(TABLE+8,4)==u32(0x40000000)and page_protect(TABLE-TABLE%PAGE)==protection.EXECUTE_READWRITE)
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
