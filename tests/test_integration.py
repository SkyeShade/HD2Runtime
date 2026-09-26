import re
import struct
import unittest

from support import ROOT, modules, run, execute, lua
import build
from hd2_archive import resource_hash, lua_resource, make_archive


class IntegrationTests(unittest.TestCase):
    def test_scheduler_preserves_returns_and_detaches(self):
        run("""
local calls=0
local previous=function(dt,a)calls=calls+1;return nil,a,42,nil end
update=previous
local w=hd2.observe{targets={{resource='amr',fields={'crosshair_type'}}},on_result=function()end}
require('hd2runtime/runtime/scheduler').attach(w)
local result={n=select('#',update(0,'x')),update(0,'x')}
assert(result.n==4 and result[1]==nil and result[2]=='x' and result[3]==42)
assert(calls==2)
w.cancel();update(0);assert(update==previous)
return 'ok'
""")

    def test_scheduler_coexists_with_later_wrapper(self):
        run("""
local function newwatch()return hd2.observe{targets={{resource='amr',fields={'crosshair_type'}}}}end
local scheduler=require('hd2runtime/runtime/scheduler')
local a=newwatch();scheduler.attach(a)
local ours=update
local later=function(dt)return ours(dt)end
update=later;a.cancel();update(0);assert(update==later)
local c=newwatch();scheduler.attach(c)
assert(update==later);c.cancel();update(0);assert(update==later)
return 'ok'
""")

    def test_callback_cancellation_is_terminal(self):
        run("""
local w
w=hd2.observe{targets={{resource='amr',fields={'crosshair_type'}}},on_result=function()w.cancel()end}
for _=1,1000 do w.tick(2);if w.status=='cancelled' then break end end
assert(w.status=='cancelled');local n=runtime.reads;w.tick(60);assert(runtime.reads==n)
return 'ok'
""")

    def test_metadata_does_not_load_ffi(self):
        execute((modules()+"""
package.preload['ffi']=function()error('unexpected native access')end
local api=require('hd2runtime/api/hd2')
assert(api.describe('amr').fields.crosshair_type.expected==3)
local _,err=api.ensure{};assert(err.code=='READ_ONLY_MILESTONE')
return 'ok'
""").encode())

    def test_native_read_only_adapter_on_own_buffer(self):
        execute((modules()+"""
local ffi=require('ffi')
local runtime=require('hd2runtime/runtime/windows_readonly')()
local bytes=ffi.new('char[5]','test')
local address=runtime.address(bytes)
assert(runtime.read(address,4)=='test')
assert(runtime.query(address).state==0x1000)
assert(runtime.system_info()==4096)
assert(runtime.sha256('abc')=='BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD')
assert(runtime.write==nil and runtime.protect==nil)
return 'ok'
""").encode())

    def test_no_write_capability_in_runtime_artifact(self):
        for name, body in build.resources().items():
            for forbidden in [b'VirtualProtect', b'WriteProcessMemory', b'ffi.copy', b'ffi.fill']:
                self.assertNotIn(forbidden, body, name)

    def test_archive_inventory_and_syntax(self):
        resources = build.resources()
        archive = make_archive({resource_hash(n):lua_resource(b) for n,b in resources.items()})
        magic, kinds, count = struct.unpack_from('<III',archive)
        self.assertEqual((magic,kinds,count),(0xF0000011,1,len(resources)))
        found = {}
        for i in range(count):
            row = struct.unpack_from('<7Q6I',archive,104+i*80)
            length, version = struct.unpack_from('<II',archive,row[2])
            self.assertEqual(version,2)
            self.assertEqual(length+8,row[7])
            found[row[0]] = archive[row[2]+8:row[2]+8+length]
        self.assertEqual(found,{resource_hash(n):b for n,b in resources.items()})
        body = 'local resources='+lua(resources)+"\nfor name,body in pairs(resources)do assert(loadstring(body,name))end;return 'ok'"
        execute(body.encode())
        entries = [(n,b) for n,b in resources.items() if b.startswith(b'-- HD2-Addon:')]
        self.assertEqual(len(entries),2)
        for name, body in entries:
            self.assertTrue(body.startswith(('-- HD2-Addon: '+name+'\n').encode()))

    def test_report_addon_runs_from_packaged_sources(self):
        source = 'local bodies='+lua(build.resources())+"""
for name,body in pairs(bodies)do
 package.preload[name]=function()return assert(loadstring(body,name))()end
 package.loaded[name]=nil
end
package.preload['hd2runtime/runtime/windows_readonly']=function()return function()return runtime end end
local report=require('mods/skyeshade/hd2runtime_report')
local initial=update
for _=1,1000 do update(0.1);if report.result or report.error then break end end
assert(report.result,report.error)
assert(report.watch.status=='cancelled' and update==nil)
local again=assert(loadstring(bodies['mods/skyeshade/hd2runtime_report']))()
assert(again==report and update==nil)
return 'ok'
"""
        run(source)


if __name__ == '__main__':
    unittest.main()
